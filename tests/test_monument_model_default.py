"""A monument's `model` is REQUIRED user input — never auto-defaulted.

For a monument, `model` is the mark's CONSTRUCTION TYPE and IGS site log §3.1
"Foundation" renders from it. Measured across the fleet (2026-08-18) the mode
"GPS stál-fjórfótur" was only ~2/3 of known marks, across four+ types
(drill-braced, pillar, pin, pole) — so auto-filling it silently publishes a
wrong §3.1 to an international registry. The audit must emit <FILL_VALUE> for
a monument's `model`, forcing the operator to supply the actual mark type.
"""


class TestNoDefault:
    def test_catalog_has_no_default(self):
        # `model` also applies to receivers/antennas/radomes; a monument default
        # would be nonsense, so it stays `~` and the audit must not invent one.
        from tostools.audit_attribute_dates import load_catalog

        entry = (load_catalog() or {}).get("model") or {}
        assert entry.get("default_value") in (None, "", "~")

    def test_no_fleet_mode_branch(self):
        # The fleet-mode auto-fill is gone: a monument's model must be supplied.
        import inspect

        from tostools import audit_missing_attributes as m

        src = inspect.getsource(m._audit_entity)
        assert "_MONUMENT_MODEL_FLEET_MODE" not in src
        assert 'code == "model" and entity_subtype == "monument"' not in src


class TestDocumentedAsRequired:
    def test_module_documents_the_requirement(self):
        import inspect

        from tostools import audit_missing_attributes as m

        src = inspect.getsource(m)
        assert "REQUIRED" in src
        assert "FILL_VALUE" in src
        assert "MONUMENT_MODEL_TO_IGS" in src
