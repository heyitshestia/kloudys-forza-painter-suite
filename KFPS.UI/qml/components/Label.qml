import QtQuick 6.7
import Kfps.Theme 1.0

Text {
    color: Theme.text
    font.family: Theme.fontFamily
    font.pixelSize: Theme.px(12)
    font.weight: Font.DemiBold
    font.capitalization: Theme.classicMode ? Font.MixedCase : Font.AllUppercase
    font.letterSpacing: 0
    renderType: Text.CurveRendering
    font.hintingPreference: Font.PreferFullHinting
    verticalAlignment: Text.AlignVCenter
    elide: Text.ElideRight
}
