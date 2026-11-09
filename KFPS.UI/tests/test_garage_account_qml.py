"""Garage navigation and first-use QML contracts; runtime coverage is in test_garage_ui."""
from pathlib import Path
import unittest

QML = Path(__file__).resolve().parents[1] / "qml"


class GarageAccountQmlTests(unittest.TestCase):
    def test_navigation_renames_only_the_display_label(self):
        for path in ("shell/Sidebar.qml", "themes/2049/ArchiveConsole.qml",
                     "themes/redline/RedlineConsole.qml", "themes/apex/ApexDashboard.qml",
                     "themes/nier/NierDashboard.qml"):
            with self.subTest(path=path):
                source = (QML / path).read_text(encoding="utf-8")
                self.assertRegex(source, r'(?:page:\s*"liveries",\s*label:|liveries:)\s*"(?:Garage|GARAGE)"')
        page = (QML / "pages/LiveryPage.qml").read_text(encoding="utf-8")
        self.assertIn('objectName: "LiveryPage"', page)
        self.assertIn('text: "Garage"', page)
        host = (QML / "components/CachedPageHost.qml").read_text(encoding="utf-8")
        self.assertIn('liveries: liveriesLoader', host)
        self.assertNotIn('garage: ', host)
        header = (QML / "shell/HeaderControls.qml").read_text(encoding="utf-8")
        self.assertIn('appController.pageSubtitle', header)
        controller = (QML.parent / "src/kfps_ui/app_controller.py").read_text(encoding="utf-8")
        self.assertIn('"liveries": "Garage"', controller)
        self.assertIn('"Owned cars, saved liveries and packages."', controller)

    def test_tabs_keep_existing_numeric_contract(self):
        page = (QML / "pages/LiveryPage.qml").read_text(encoding="utf-8")
        for label, index in (("Saved Liveries", 0), ("Packages", 1), ("My Cars", 2)):
            self.assertRegex(page, rf'LibraryTab\s*\{{[^}}]*text: "{label}";[^}}]*root.libraryTab = {index}')
        self.assertIn('property int libraryTab: garage ? 2 : 0', page)
        self.assertIn('pageReady && pageActive && showGallery && libraryTab === 2 && garage', page)
        self.assertIn('garage.enter()', page)
        self.assertNotIn('garage.activate()', page)
        self.assertNotIn('garage.enter()', (QML / "Main.qml").read_text(encoding="utf-8"))

    def test_account_choices_bind_to_confirmed_service_selection(self):
        browser = (QML / "components/GarageBrowser.qml").read_text(encoding="utf-8")
        self.assertIn('label: "Choose an account"', browser)
        self.assertIn('account.id === service.selectedAccountId', browser)
        self.assertIn('currentIndex: root.selectedAccountIndex', browser)
        self.assertRegex(browser, r'onActivated: function\(index\)\s*\{\s*if \(index > 0\) root.service.selectAccount')
        self.assertNotRegex(browser, r'onCurrentIndexChanged:\s*.*selectAccount')
        for name in ('garageAccountPicker', 'garageRescanAccounts', 'garageChooseSource',
                     'garageAccountStatus', 'garageEmptyTitle', 'garageSummary', 'garageSnapshotDate'):
            self.assertIn(f'objectName: "{name}"', browser)
        self.assertIn('root.service.rescanAccounts()', browser)
        self.assertIn('root.service.chooseSource()', browser)
        self.assertIn('labelTextFormat: Text.PlainText', browser)
        self.assertIn('"With livery: "', browser)
        self.assertIn('"Snapshot: "', browser)
        self.assertNotIn('Last refreshed:', browser)


if __name__ == "__main__":
    unittest.main()
