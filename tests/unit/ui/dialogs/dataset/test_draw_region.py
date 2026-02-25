"""Unit tests for DrawRegion (pure numpy coordinate logic)."""

import numpy as np

from XBrainLab.ui.dialogs.dataset.data_splitting_dialog import DrawRegion


class TestDrawRegionInit:
    def test_initial_canvas_zeros(self):
        r = DrawRegion(4, 3)
        assert r.from_canvas.shape == (4, 3)
        assert r.to_canvas.shape == (4, 3)
        np.testing.assert_array_equal(r.from_canvas, 0)
        np.testing.assert_array_equal(r.to_canvas, 0)

    def test_initial_coords_zero(self):
        r = DrawRegion(5, 5)
        assert r.from_x == 0
        assert r.from_y == 0
        assert r.to_x == 0
        assert r.to_y == 0


class TestDrawRegionReset:
    def test_reset_clears_canvas(self):
        r = DrawRegion(3, 3)
        r.from_canvas[:] = 1
        r.to_canvas[:] = 2
        r.reset()
        np.testing.assert_array_equal(r.from_canvas, 0)
        np.testing.assert_array_equal(r.to_canvas, 0)


class TestDrawRegionSetFrom:
    def test_set_from_stores_coords_and_resets(self):
        r = DrawRegion(4, 4)
        r.from_canvas[:] = 5
        r.set_from(1, 2)
        assert r.from_x == 1
        assert r.from_y == 2
        # reset should have zeroed canvases
        np.testing.assert_array_equal(r.from_canvas, 0)


class TestDrawRegionSetTo:
    def test_set_to_fills_region(self):
        r = DrawRegion(4, 4)
        r.set_from(0, 0)
        r.set_to(2, 3, from_w=10, to_w=20)
        assert r.to_x == 2
        assert r.to_y == 3
        # region [0:2, 0:3] should be filled
        np.testing.assert_array_equal(r.from_canvas[0:2, 0:3], 10)
        np.testing.assert_array_equal(r.to_canvas[0:2, 0:3], 20)
        # outside region should be zero
        assert r.from_canvas[3, 3] == 0
        assert r.to_canvas[3, 3] == 0


class TestDrawRegionSetToRef:
    def test_copies_from_reference(self):
        ref = DrawRegion(4, 4)
        ref.set_from(0, 0)
        ref.set_to(3, 3, from_w=5, to_w=15)

        r = DrawRegion(4, 4)
        r.set_from(1, 1)
        r.set_to_ref(3, 3, ref)
        # should copy ref's values in [1:3, 1:3]
        np.testing.assert_array_equal(r.from_canvas[1:3, 1:3], 5)
        np.testing.assert_array_equal(r.to_canvas[1:3, 1:3], 15)


class TestDrawRegionChangeTo:
    def test_updates_coords_only(self):
        r = DrawRegion(4, 4)
        r.set_from(0, 0)
        r.set_to(2, 2, from_w=1, to_w=2)
        old_from = r.from_canvas.copy()
        old_to = r.to_canvas.copy()
        r.change_to(3, 3)
        assert r.to_x == 3
        assert r.to_y == 3
        # canvas data unchanged
        np.testing.assert_array_equal(r.from_canvas, old_from)
        np.testing.assert_array_equal(r.to_canvas, old_to)


class TestDrawRegionDecreaseWTail:
    def test_shrink_tail(self):
        r = DrawRegion(4, 4)
        r.set_from(0, 0)
        r.set_to(2, 2, from_w=0, to_w=10)
        r.decrease_w_tail(0.5)
        # to_canvas = (10 - 0) * 0.5 + 0 = 5
        np.testing.assert_array_equal(r.to_canvas[0:2, 0:2], 5)


class TestDrawRegionDecreaseWHead:
    def test_shrink_head(self):
        r = DrawRegion(4, 4)
        r.set_from(0, 0)
        r.set_to(2, 2, from_w=0, to_w=10)
        r.decrease_w_head(0.5)
        # from_canvas = (10 - 0) * 0.5 + 0 = 5
        np.testing.assert_array_equal(r.from_canvas[0:2, 0:2], 5)


class TestDrawRegionCopy:
    def test_deep_copy(self):
        src = DrawRegion(3, 3)
        src.set_from(1, 1)
        src.set_to(3, 3, from_w=7, to_w=14)

        dst = DrawRegion(3, 3)
        dst.copy(src)

        assert dst.from_x == 1
        assert dst.from_y == 1
        assert dst.to_x == 3
        assert dst.to_y == 3
        np.testing.assert_array_equal(dst.from_canvas, src.from_canvas)
        np.testing.assert_array_equal(dst.to_canvas, src.to_canvas)
        # confirm deep copy — mutation of src shouldn't affect dst
        src.from_canvas[2, 2] = 999
        assert dst.from_canvas[2, 2] != 999


class TestDrawRegionMask:
    def test_mask_adjusts_canvas(self):
        main = DrawRegion(4, 4)
        main.set_from(0, 0)
        main.set_to(3, 3, from_w=0, to_w=10)

        mask_region = DrawRegion(4, 4)
        mask_region.set_from(1, 1)
        mask_region.set_to(3, 3, from_w=2, to_w=8)

        # Save original to_canvas for comparison
        original_to = main.to_canvas.copy()

        main.mask(mask_region)
        # The mask should have modified the to_canvas in the masked region
        # Unmasked cells (row 0 or col 0) should remain 10
        assert main.to_canvas[0, 0] == 10.0
        # The masked sub-region [1:3, 1:3] should have been adjusted
        # (values reduced where mask from_canvas != to_canvas)
        assert not np.array_equal(main.to_canvas, original_to)
