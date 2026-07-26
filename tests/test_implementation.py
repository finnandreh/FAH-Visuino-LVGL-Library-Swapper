from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lvgl_visuino_setup_manager.audit import AuditRepository
from lvgl_visuino_setup_manager.controller import ApplicationController
from lvgl_visuino_setup_manager.implementation import (
    CustomCodeHooks,
    ImplementationError,
    ImplementationService,
)
from lvgl_visuino_setup_manager.paths import AppPaths
from lvgl_visuino_setup_manager.registry import RegistryRepository, RegistryService
from lvgl_visuino_setup_manager.setup_service import SetupService


class ImplementationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = AppPaths.discover(self.root / "appdata")
        self.paths.ensure()
        self.service = ImplementationService(self.paths)
        self.setup_root = self.root / "profiles" / "Release A"
        self.setup = self.setup_root / "libraries"
        (self.setup / "Mitov").mkdir(parents=True)
        (self.setup / "VisuinoPro").mkdir()
        self.source = self.root / "standalone"
        (self.source / "src" / "ui").mkdir(parents=True)
        (self.source / "include").mkdir()
        (self.source / "lib" / "ESP32_Display_Panel" / "src").mkdir(
            parents=True
        )
        (self.source / "src" / "main.cpp").write_text(
            "void setup() {}\nvoid loop() {}\n",
            encoding="utf-8",
        )
        (self.source / "src" / "lvgl_port.cpp").write_text(
            "void lvgl_port_init() {}\n",
            encoding="utf-8",
        )
        (self.source / "src" / "lvgl_port.h").write_text(
            "#pragma once\nvoid lvgl_port_init();\n",
            encoding="utf-8",
        )
        (self.source / "src" / "ui" / "dashboard.cpp").write_text(
            "void dashboard_create() {}\n",
            encoding="utf-8",
        )
        self.arduino_sketch = (
            "#include <Waveshare43Device.h>\n\n"
            "void setup() {\n"
            "  waveshare43_example::begin();\n"
            "}\n\n"
            "void loop() {\n"
            "  waveshare43_example::loop();\n"
            "}\n"
        )
        (self.source / "StandaloneDisplay.ino").write_text(
            self.arduino_sketch,
            encoding="utf-8",
        )
        self.source_readme = "# Standalone Display\n\nManual binding guide.\n"
        (self.source / "README.md").write_text(
            self.source_readme,
            encoding="utf-8",
        )
        self.ui_elements_document = {
            "schemaVersion": 1,
            "project": "StandaloneDisplay",
            "bridgeNamespace": "standalone_display",
            "elements": [
                {
                    "id": "action_button",
                    "name": "Action",
                    "screen": "Main",
                    "type": "button",
                    "lvglObject": "ui_action_button",
                    "direction": "event",
                    "valueType": "event",
                    "events": ["LV_EVENT_CLICKED"],
                    "readApi": "",
                    "writeApi": "",
                    "description": "Triggers the primary action.",
                },
                {
                    "id": "level_slider",
                    "name": "Level",
                    "screen": "Main",
                    "type": "slider",
                    "lvglObject": "ui_level_slider",
                    "direction": "bidirectional",
                    "valueType": "int",
                    "range": {
                        "min": 0,
                        "max": 100,
                        "step": 1,
                        "unit": "%",
                    },
                    "events": ["LV_EVENT_VALUE_CHANGED"],
                    "readApi": "lv_slider_get_value(ui_level_slider)",
                    "writeApi": (
                        "standalone_display::set_level_slider(value)"
                    ),
                    "visuinoInputCode": (
                        "standalone_display::set_level_slider(AValue);"
                    ),
                    "visuinoLoopCode": (
                        "Integer1.Send(standalone_display::get_level_slider());"
                    ),
                    "description": "A manually linked level value.",
                },
            ],
        }
        (self.source / "ui-elements.json").write_text(
            json.dumps(self.ui_elements_document, indent=2),
            encoding="utf-8",
        )
        (self.source / "include" / "lv_conf.h").write_text(
            "#define LV_COLOR_DEPTH 16\n",
            encoding="utf-8",
        )
        (self.source / "lib" / "ESP32_Display_Panel" / "library.properties").write_text(
            "name=ESP32_Display_Panel\nversion=1.0.0\n",
            encoding="utf-8",
        )
        (
            self.source
            / "lib"
            / "ESP32_Display_Panel"
            / "src"
            / "panel.cpp"
        ).write_text("void panel_begin() {}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_loose_project_plan_routes_entrypoint_config_ui_and_dependencies(self) -> None:
        plan = self.service.plan_import(
            "setup_a",
            self.setup,
            self.source,
            "WaveshareBridge",
        )
        destinations = {
            str(item.destination.relative_to(self.setup)) for item in plan.files
        }

        self.assertEqual("loose_source", plan.mode)
        self.assertIn("lv_conf.h", destinations)
        self.assertIn(
            str(Path("WaveshareBridge") / "extras" / "original" / "src" / "main.cpp"),
            destinations,
        )
        self.assertNotIn(
            str(Path("WaveshareBridge") / "src" / "main.cpp"),
            destinations,
        )
        self.assertIn(
            str(Path("WaveshareBridge") / "src" / "ui" / "dashboard.cpp"),
            destinations,
        )
        self.assertIn(
            str(Path("ESP32_Display_Panel") / "src" / "panel.cpp"),
            destinations,
        )
        self.assertEqual(self.arduino_sketch, plan.arduino_sketch)
        self.assertEqual("source:StandaloneDisplay.ino", plan.sketch_origin)
        self.assertEqual("source:ui-elements.json", plan.ui_elements_origin)
        self.assertEqual(2, len(plan.ui_elements))
        self.assertEqual("ui_action_button", plan.ui_elements[0].lvgl_object)
        self.assertEqual("0…100, step 1 %", plan.ui_elements[1].range_text)
        self.assertEqual(
            "standalone_display",
            plan.ui_elements[1].bridge_namespace,
        )
        self.assertEqual(
            "standalone_display::set_level_slider(AValue);",
            plan.ui_elements[1].write_copy_text,
        )
        self.assertEqual(
            "Integer1.Send(standalone_display::get_level_slider());",
            plan.ui_elements[1].read_copy_text,
        )
        self.assertIn(
            str(
                Path("WaveshareBridge")
                / "extras"
                / "visuino-import.ino"
            ),
            destinations,
        )
        self.assertIn(
            str(
                Path("WaveshareBridge")
                / "extras"
                / "ui-elements.json"
            ),
            destinations,
        )
        self.assertIn(
            str(Path("WaveshareBridge") / "extras" / "README.md"),
            destinations,
        )

    def test_install_verifies_manifest_and_preserves_hooks_on_update(self) -> None:
        first_plan = self.service.plan_import(
            "setup_a",
            self.setup,
            self.source,
            "WaveshareBridge",
        )
        first = self.service.install(first_plan)
        self.assertEqual(
            self.arduino_sketch,
            self.service.load_visuino_sketch(
                self.setup,
                "WaveshareBridge",
            ),
        )
        loaded_elements = self.service.load_ui_elements(
            self.setup,
            "WaveshareBridge",
        )
        self.assertEqual(2, len(loaded_elements))
        self.assertEqual("ui_level_slider", loaded_elements[1].lvgl_object)
        self.assertEqual(
            self.source_readme,
            (
                self.setup
                / "WaveshareBridge"
                / "extras"
                / "README.md"
            ).read_text(encoding="utf-8"),
        )
        hooks = CustomCodeHooks(
            includes="#include <lvgl_port.h>",
            globals="int display_state = 0;",
            setup="lvgl_port_init();",
            loop="display_state++;",
        )
        self.service.save_hooks(self.setup, "WaveshareBridge", hooks)

        validation = self.service.validate(self.setup, "WaveshareBridge")
        self.assertTrue(validation.is_valid, validation.warnings)
        self.assertTrue(first.manifest_path.is_file())
        manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual("external_standalone", manifest["packageId"])
        self.assertTrue(
            all("sha256" not in entry for entry in manifest["files"])
        )
        self.assertIn(
            "#include <lvgl_port.h>",
            self.service.load_visuino_sketch(
                self.setup,
                "WaveshareBridge",
            ),
        )

        source_file = self.source / "src" / "lvgl_port.cpp"
        source_file.write_text("void lvgl_port_init() { int changed = 1; }\n", encoding="utf-8")
        second_plan = self.service.plan_import(
            "setup_a",
            self.setup,
            self.source,
            "WaveshareBridge",
        )
        second = self.service.install(second_plan)

        loaded_hooks = self.service.load_hooks(self.setup, "WaveshareBridge")
        self.assertEqual(hooks, loaded_hooks)
        self.assertEqual(
            self.arduino_sketch,
            self.service.load_visuino_sketch(
                self.setup,
                "WaveshareBridge",
            ),
        )
        self.assertTrue(
            (second.backup_path / "WaveshareBridge" / "src" / "lvgl_port.cpp").is_file()
        )
        self.assertIn(
            "changed",
            (self.setup / "WaveshareBridge" / "src" / "lvgl_port.cpp").read_text(
                encoding="utf-8"
            ),
        )

    def test_arduino_libraries_directory_is_preserved_at_setup_root(self) -> None:
        bundle = self.root / "waveshare-demo"
        (bundle / "WaveshareDemo.ino").parent.mkdir(parents=True)
        (bundle / "WaveshareDemo.ino").write_text(
            "void setup() {}\nvoid loop() {}\n",
            encoding="utf-8",
        )
        libraries = bundle / "Arduino" / "libraries"
        (libraries / "lvgl" / "src").mkdir(parents=True)
        (libraries / "lvgl" / "library.properties").write_text(
            "name=lvgl\nversion=8.4.0\n",
            encoding="utf-8",
        )
        (libraries / "lvgl" / "src" / "lvgl.h").write_text(
            "#pragma once\n",
            encoding="utf-8",
        )
        (libraries / "lv_conf.h").write_text(
            "#define LV_COLOR_DEPTH 16\n",
            encoding="utf-8",
        )
        (libraries / "Mitov").mkdir()
        (libraries / "Mitov" / "do_not_replace.h").write_text(
            "#pragma once\n",
            encoding="utf-8",
        )

        plan = self.service.plan_import(
            "setup_a",
            self.setup,
            bundle,
            "WaveshareBridge",
        )
        destinations = {
            str(item.destination.relative_to(self.setup)) for item in plan.files
        }

        self.assertEqual("libraries_directory", plan.mode)
        self.assertIn(str(Path("lvgl") / "src" / "lvgl.h"), destinations)
        self.assertIn("lv_conf.h", destinations)
        self.assertFalse(any(path.startswith("Mitov") for path in destinations))
        self.assertTrue(any("protected" in item.lower() for item in plan.warnings))

    def test_hooks_can_create_a_manual_metadata_library(self) -> None:
        hooks = CustomCodeHooks(
            includes="#include <lvgl.h>",
            setup="lv_init();",
        )
        path = self.service.save_hooks(
            self.setup,
            "ManualDisplay",
            hooks,
        )

        self.assertTrue(path.is_file())
        self.assertTrue((self.setup / "ManualDisplay" / "library.properties").is_file())
        self.assertEqual(
            hooks,
            self.service.load_hooks(self.setup, "ManualDisplay"),
        )
        migrated_sketch = self.service.load_visuino_sketch(
            self.setup,
            "ManualDisplay",
        )
        self.assertIn("#include <lvgl.h>", migrated_sketch)
        self.assertIn("void setup()", migrated_sketch)
        self.assertIn("lv_init();", migrated_sketch)
        self.assertTrue(self.service.validate(self.setup, "ManualDisplay").is_valid)

    def test_source_without_root_ino_is_rejected(self) -> None:
        (self.source / "StandaloneDisplay.ino").unlink()
        with self.assertRaisesRegex(
            ImplementationError,
            "exactly one .ino file at its root; found 0",
        ):
            self.service.plan_import(
                "setup_a",
                self.setup,
                self.source,
                "MissingSketchBridge",
            )

    def test_source_with_multiple_root_ino_files_is_rejected(self) -> None:
        (self.source / "SecondSketch.ino").write_text(
            "void setup() {}\nvoid loop() {}\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            ImplementationError,
            "exactly one .ino file at its root; found 2",
        ):
            self.service.plan_import(
                "setup_a",
                self.setup,
                self.source,
                "AmbiguousSketchBridge",
            )

    def test_missing_ui_element_registry_is_allowed_with_empty_inventory(self) -> None:
        (self.source / "ui-elements.json").unlink()
        plan = self.service.plan_import(
            "setup_a",
            self.setup,
            self.source,
            "LegacyBridge",
        )

        self.assertEqual((), plan.ui_elements)
        self.assertEqual("missing", plan.ui_elements_origin)
        self.assertTrue(
            any("No ui-elements.json" in warning for warning in plan.warnings)
        )

    def test_invalid_ui_element_registry_is_rejected(self) -> None:
        invalid = dict(self.ui_elements_document)
        invalid["elements"] = [
            self.ui_elements_document["elements"][0],
            {
                **self.ui_elements_document["elements"][1],
                "id": "ACTION_BUTTON",
            },
        ]
        (self.source / "ui-elements.json").write_text(
            json.dumps(invalid),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ImplementationError, "duplicate id"):
            self.service.plan_import(
                "setup_a",
                self.setup,
                self.source,
                "InvalidElementsBridge",
            )

    def test_invalid_ui_element_bridge_namespace_is_rejected(self) -> None:
        invalid = {
            **self.ui_elements_document,
            "bridgeNamespace": "standalone-display",
        }
        (self.source / "ui-elements.json").write_text(
            json.dumps(invalid),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            ImplementationError,
            "valid C\\+\\+ namespace",
        ):
            self.service.plan_import(
                "setup_a",
                self.setup,
                self.source,
                "InvalidNamespaceBridge",
            )

    def test_legacy_ui_element_registry_without_namespace_still_loads(self) -> None:
        legacy = {
            key: value
            for key, value in self.ui_elements_document.items()
            if key != "bridgeNamespace"
        }
        legacy["elements"] = [
            {
                key: value
                for key, value in element.items()
                if key not in {"visuinoInputCode", "visuinoLoopCode"}
            }
            for element in legacy["elements"]
        ]
        (self.source / "ui-elements.json").write_text(
            json.dumps(legacy),
            encoding="utf-8",
        )

        plan = self.service.plan_import(
            "setup_a",
            self.setup,
            self.source,
            "LegacyNamespaceBridge",
        )

        slider = plan.ui_elements[1]
        self.assertEqual("", slider.bridge_namespace)
        self.assertEqual(slider.read_api, slider.read_copy_text)
        self.assertEqual(slider.write_api, slider.write_copy_text)

    def test_source_inside_setup_is_rejected(self) -> None:
        nested = self.setup / "incoming"
        nested.mkdir()
        with self.assertRaisesRegex(ImplementationError, "inside it"):
            self.service.plan_import(
                "setup_a",
                self.setup,
                nested,
                "UnsafeBridge",
            )

    def test_controller_blocks_install_while_visuino_is_running(self) -> None:
        repository = RegistryRepository(
            self.root / "registry.json",
            self.root / "registry.previous.json",
        )
        registry = RegistryService(repository)
        client_id = registry.create_client("Client")
        project_id = registry.create_project(client_id, "Project")
        setup_id = registry.create_setup(
            client_id,
            project_id,
            "Release A",
            self.setup_root,
        )

        class RunningActivationStub:
            @staticmethod
            def running_check() -> bool:
                return True

        controller = ApplicationController(
            registry=registry,
            setup_service=SetupService(),
            implementation_service=self.service,
            activation_service=RunningActivationStub(),  # type: ignore[arg-type]
            audit=AuditRepository(self.root / "audit.jsonl"),
        )
        plan = controller.plan_implementation_import(
            setup_id,
            self.source,
            "BlockedBridge",
        )

        with self.assertRaisesRegex(ImplementationError, "Close Visuino Pro"):
            controller.install_implementation(plan)
        self.assertFalse((self.setup / "BlockedBridge").exists())


if __name__ == "__main__":
    unittest.main()
