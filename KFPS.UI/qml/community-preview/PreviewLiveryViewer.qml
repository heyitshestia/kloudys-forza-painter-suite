import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebEngine
import Kfps.Theme 1.0

PreviewDialog {
    id: dialog
    property var ui
    readonly property var viewer: preview.liveryViewer
    // WebEngine reloads on repeated URL assignments, including status signals.
    readonly property string viewerSessionUrl: viewer ? viewer.viewerUrl : ""
    anchors.centerIn: parent
    modal: true
    width: parent.width - 40; height: parent.height - 40
    title: ui("3D livery preview", "리버리 3D 미리보기")
    closePolicy: Popup.CloseOnEscape
    onClosed: preview.closeRender()
    contentItem: ColumnLayout {
        RowLayout {
            Layout.fillWidth: true
            PreviewText { Layout.fillWidth: true; text: preview.selected.title || ""; textSize: 18 }
            PreviewButton { objectName: "CloseLiveryRender"; text: "X"; minimumWidth: 36; hint: dialog.ui("Close 3D preview", "3D 미리보기 닫기"); onClicked: dialog.close() }
        }
        Item {
            Layout.fillWidth: true; Layout.fillHeight: true
            Loader {
                anchors.fill: parent
                active: dialog.visible && dialog.viewerSessionUrl.length > 0
                sourceComponent: WebEngineView {
                    id: carView
                    objectName: "CommunityCarView"
                    url: dialog.viewerSessionUrl
                    backgroundColor: "#090b0e"
                    settings.localContentCanAccessRemoteUrls: false
                    settings.localContentCanAccessFileUrls: false
                    settings.javascriptCanOpenWindows: false
                    onRenderProcessPidChanged: if (dialog.viewer) dialog.viewer.viewerProcess(url.toString(), renderProcessPid)
                    onRenderProcessTerminated: function(status, code) { if (dialog.viewer) dialog.viewer.viewerFailed(url.toString(), "Renderer stopped: " + status + ", " + code) }
                    onLoadingChanged: function(request) { if (dialog.viewer && request.status === WebEngineView.LoadFailedStatus) dialog.viewer.viewerFailed(url.toString(), request.errorString) }
                    onJavaScriptConsoleMessage: function(level, message) {
                        if (dialog.viewer && message.indexOf("KFPS_VIEWER:") === 0) {
                            dialog.viewer.viewerProcess(url.toString(), renderProcessPid)
                            dialog.viewer.viewerEvent(url.toString(), message.slice(12))
                        }
                    }
                    Timer {
                        interval: 5000; repeat: true; running: !!dialog.viewer && dialog.visible
                        onTriggered: {
                            const session = carView.url.toString()
                            carView.runJavaScript("JSON.stringify({event:'sample',diagnostics:window.__kfpsViewerDiagnostics?.()})", function(result) {
                                if (dialog.viewer && typeof result === "string") dialog.viewer.viewerEvent(session, result)
                            })
                        }
                    }
                    Component.onDestruction: { stop(); url = "about:blank" }
                }
            }
            ColumnLayout {
                anchors.centerIn: parent; width: Math.min(parent.width - 40, 620)
                visible: !!dialog.viewer && !dialog.viewer.viewerReady
                BusyIndicator { Layout.alignment: Qt.AlignHCenter; running: dialog.visible && !!dialog.viewer && dialog.viewer.running }
                PreviewText { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: dialog.viewer ? dialog.viewer.status : "" }
                PreviewText { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; color: Theme.muted; text: dialog.viewer ? dialog.viewer.summary : "" }
                PreviewButton { Layout.alignment: Qt.AlignHCenter; visible: !!dialog.viewer && !dialog.viewer.running && !dialog.viewer.viewerUrl; text: dialog.ui("Choose FH6 game folder", "FH6 게임 폴더 선택"); onClicked: dialog.viewer.chooseGameFolder() }
            }
        }
    }
}
