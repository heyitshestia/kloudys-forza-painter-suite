import QtQuick 6.7
import Kfps.Theme 1.0

Column {
    id: root

    property alias title: titleText.text
    property alias subtitle: subtitleText.text
    spacing: Theme.px(4)

    Text {
        id: titleText
        width: parent.width
        color: Theme.text
        font.family: Theme.displayFamily
        font.pixelSize: Theme.px(Theme.classicMode ? 17 : 21)
        font.weight: Theme.classicMode ? Font.Bold : Font.DemiBold
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
    }

    Text {
        id: subtitleText
        width: parent.width
        color: Theme.muted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(11.5)
        wrapMode: Text.Wrap
        lineHeight: 1.28
    }
}
