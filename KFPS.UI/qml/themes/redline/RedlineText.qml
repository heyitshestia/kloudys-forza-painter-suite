import QtQuick 6.7
import Kfps.Theme 1.0

Text {
    property bool heading: false
    color: Theme.text
    font.family: heading ? Theme.displayFamily : Theme.fontFamily
    font.weight: heading ? Font.Bold : Font.Normal
    font.pixelSize: Theme.px(heading ? 18 : 14)
    font.letterSpacing: 0
    elide: Text.ElideRight
    textFormat: Text.PlainText
}
