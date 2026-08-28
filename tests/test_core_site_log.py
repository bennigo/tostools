class TestPrefetchedMetadataSeam:
    """`build_site_log` can render from metadata the caller already holds.

    `client` was injectable at this layer while the layer below —
    `legacy.gps_metadata_functions.site_log` — still did its own live TOS
    fetch. The renderer has advertised `station=` / `device_sessions=` since it
    was unified; nothing threaded them, so receivers' site-log tests passed
    ONLY because they reached production TOS at 10.254.0.12.
    """

    def test_prefetched_metadata_reaches_the_renderer(self, monkeypatch):
        from tostools.core import site_log as mod

        seen = {}

        def _fake_render(sid, **kw):
            seen.update(kw)
            seen["sid"] = sid
            return "SITE LOG"

        monkeypatch.setattr(
            "tostools.legacy.gps_metadata_functions.site_log", _fake_render
        )
        out = mod.build_site_log(
            "rhof",
            agencies={},  # non-None, so no TOS lookup for agencies either
            station_metadata={"marker": "rhof"},
            device_sessions=[],
        )
        assert out == "SITE LOG"
        assert seen["station"] == {"marker": "rhof"}
        assert seen["device_sessions"] == []

    def test_omitting_them_still_means_a_live_fetch(self, monkeypatch):
        """Absence must keep the existing behaviour exactly — None, not {}.

        A caller that does not supply metadata gets the renderer's own fetch,
        which is what every production path does today. Passing an empty dict
        instead of None would make the renderer think it had metadata and emit
        an empty site log.
        """
        from tostools.core import site_log as mod

        seen = {}

        def _fake_render(sid, **kw):
            seen.update(kw)
            return "SITE LOG"

        monkeypatch.setattr(
            "tostools.legacy.gps_metadata_functions.site_log", _fake_render
        )
        mod.build_site_log("rhof", agencies={})
        assert seen["station"] is None
        assert seen["device_sessions"] is None
