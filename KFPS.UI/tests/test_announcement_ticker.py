from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "qml/shell/AnnouncementTicker.qml").read_text()


class AnnouncementTickerMotionTests(unittest.TestCase):
    def test_scroll_has_one_guarded_restart_owner(self):
        restart = SOURCE.split("function restartScroll()", 1)[1].split("onMotionAllowedChanged", 1)[0]
        self.assertLess(restart.index("restartTimer.stop()"), restart.index("if (motionAllowed)"))
        self.assertLess(restart.index("scrollAnimation.stop()"), restart.index("if (motionAllowed)"))
        timer = SOURCE.split("id: restartTimer", 1)[1].split("RowLayout", 1)[0]
        self.assertLess(timer.index("if (!root.motionAllowed)"), timer.index("scrollAnimation.restart()"))
        scroll = SOURCE.split("id: scrollAnimation", 1)[1].split("Text {", 1)[0]
        self.assertNotIn("running:", scroll)

    def test_inactive_hidden_paused_and_reduced_motion_stop_scroll(self):
        gate = SOURCE.split("readonly property bool motionAllowed:", 1)[1].splitlines()[0]
        for condition in ("visible", "Window.window.active", "Window.Minimized", "!Theme.reducedMotion", "!paused", "!screenshotMode"):
            self.assertIn(condition, gate)
        self.assertIn("onMotionAllowedChanged: restartScroll()", SOURCE)
        self.assertIn("visible: !root.motionAllowed", SOURCE)
        self.assertIn("running: announcementService.checking && root.motionAllowed", SOURCE)


if __name__ == "__main__":
    unittest.main()
