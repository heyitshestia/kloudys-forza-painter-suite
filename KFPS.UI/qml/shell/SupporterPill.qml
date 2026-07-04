import QtQuick 6.7
import QtQuick.Effects 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    property bool compact: false

    visible: supporterService.unlocked
    width: Theme.px(compact ? 150 : 178)
    height: Theme.px(34)
    radius: height / 2
    soft: true

    RowLayout {
        anchors.centerIn: parent
        spacing: Theme.px(6)

        Text {
            text: "✦"
            color: Theme.primaryBright
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.compact ? 13 : 15)
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
        }

        Text {
            text: "supporter"
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.compact ? 10.8 : 11.8)
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
        }

        Text {
            text: "✦"
            color: Theme.primaryBright
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(root.compact ? 13 : 15)
            font.weight: Font.DemiBold
            verticalAlignment: Text.AlignVCenter
        }
    }

    layer.enabled: Theme.glassEffects && !screenshotMode
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: Theme.primary
        shadowBlur: 0.72
        shadowOpacity: 0.44
        shadowVerticalOffset: Theme.px(2)
    }
}
