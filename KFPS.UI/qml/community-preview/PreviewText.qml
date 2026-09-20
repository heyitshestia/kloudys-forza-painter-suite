import QtQuick
import Kfps.Theme 1.0

Text {
    property int textSize: Math.round(Theme.px(14))
    property int textWeight: Font.Normal
    property bool underlineText: false
    color: Theme.text
    font.family: Theme.fontFamily
    font.pixelSize: Theme.typeSize(textSize)
    font.weight: Math.max(textWeight, Theme.technicalTypographyEnabled ? Font.Medium : Font.Normal)
    font.underline: underlineText
    font.letterSpacing: 0
    renderType: Text.CurveRendering
    wrapMode: Text.Wrap
    textFormat: Text.PlainText
}
