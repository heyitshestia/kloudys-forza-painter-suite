import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    objectName: "CommunityPage"
    anchors.fill: parent
    clip: true

    property int activeTab: 0
    property bool revisionMode: false
    property string uploadClassification: ""
    property bool uploadSupporterOnly: false
    property string lastUploadPath: ""
    property string pendingUploadPath: ""
    property string metadataResetForPath: ""
    property string profileLoadedFor: ""
    property string pendingCommunityUsername: ""
    property string testOverlay: ""
    readonly property bool wide: Theme.logical(width) >= 1040
    readonly property bool compactHeight: Theme.logical(height) < 720
    readonly property bool supporterCatalogLocked: communityService.selectedScopeIndex === 3
                                                   && !communityService.supporterAccess
    readonly property bool activeSupporterKey: communityService.supporterKeyConnected
    readonly property bool headerAlignmentAvailable: root.activeTab === 0 && root.wide
                                                     && !root.supporterCatalogLocked
                                                     && browsePanel.width > 0 && detailPanel.width > 0
    readonly property real headerSourceCenterX: browsePanel.x + browsePanel.width / 2
    readonly property real headerPreviewCenterX: detailPanel.x + detailPanel.width / 2
    readonly property real headerBannerLeftX: 0
    readonly property real headerBannerRightX: width

    ButtonGroup {
        id: uploadClassificationGroup
        exclusive: true
    }

    ButtonGroup {
        id: uploadAudienceGroup
        exclusive: true
    }

    function uploadLicense() {
        var values = communityService.licenses
        return uploadLicenseBox.currentIndex >= 0 && uploadLicenseBox.currentIndex < values.length
                ? values[uploadLicenseBox.currentIndex] : "kfps-community-share-v1"
    }

    function syncUploadSelection() {
        if (communityService.uploadPath && communityService.uploadPath !== root.lastUploadPath) {
            root.resetMetadataForNewUpload(communityService.uploadPath)
            root.lastUploadPath = communityService.uploadPath
            root.pendingUploadPath = communityService.uploadPath
            uploadTitle.text = communityService.uploadName
            compatibilityConfirmation.checked = false
        }
    }

    function comparableLocalPath(value) {
        return String(value || "").replace(/\//g, "\\").toLowerCase()
    }

    function resetMetadataForNewUpload(path) {
        var candidate = root.comparableLocalPath(path)
        if (root.revisionMode || candidate.length === 0
                || candidate === root.comparableLocalPath(root.metadataResetForPath))
            return
        root.metadataResetForPath = String(path)
        uploadDescription.text = ""
        uploadTags.text = ""
        root.uploadClassification = ""
        root.uploadSupporterOnly = false
        rightsConfirmation.checked = false
        compatibilityConfirmation.checked = false
        revisionNote.text = ""
    }

    function uploadTileSelected(path) {
        var selected = communityService.uploadPath || root.pendingUploadPath
        return selected.length > 0 && root.comparableLocalPath(selected) === root.comparableLocalPath(path)
    }

    function prepareUploadPath(path) {
        if (!path || communityService.busy)
            return
        root.resetMetadataForNewUpload(path)
        root.pendingUploadPath = String(path)
        jsonService.selectPath(String(path))
        communityService.selectUploadJson(String(path))
    }

    function syncProfile() {
        if (!communityService.authenticated || communityService.usernameRequired)
            return
        if (root.profileLoadedFor === communityService.username)
            return
        root.profileLoadedFor = communityService.username
        profileBio.text = String(communityService.sessionUser.bio || "")
        profileWebsite.text = String(communityService.sessionUser.website_url || "")
    }

    function prepareRevision() {
        var selected = communityService.selectedArtwork
        root.revisionMode = true
        uploadTitle.text = String(selected.title || "")
        uploadDescription.text = String(selected.description || "")
        uploadTags.text = String(selected.tagsText || "")
        root.uploadClassification = String(selected.classification || "toolmade")
        root.uploadSupporterOnly = Boolean(selected.supporterOnly)
        var categoryIndex = uploadCategory.find(String(selected.category || "Other"))
        uploadCategory.currentIndex = categoryIndex >= 0 ? categoryIndex : 1
        var licenseIndex = communityService.licenses.indexOf(String(selected.license || ""))
        uploadLicenseBox.currentIndex = licenseIndex >= 0 ? licenseIndex : 0
        rightsConfirmation.checked = false
        compatibilityConfirmation.checked = false
        revisionNote.text = ""
        root.activeTab = 1
    }

    function openLogin() {
        if (!communityService.authenticated)
            loginDialog.open()
    }

    function openArtworkInspector(index) {
        if (index >= 0)
            communityService.selectArtwork(index)
        if (!communityService.hasSelection)
            return
        artworkInspector.previewZoom = 1.0
        artworkInspector.open()
        artworkInspector.forceActiveFocus()
    }

    onActiveTabChanged: {
        if (activeTab === 2)
            communityService.refreshAccount()
    }

    onTestOverlayChanged: {
        if (testOverlay === "login")
            loginDialog.open()
        else if (testOverlay === "inspector")
            root.openArtworkInspector(Math.max(0, communityService.selectedIndex))
    }

    Component.onCompleted: {
        root.syncUploadSelection()
        root.syncProfile()
    }

    Connections {
        target: communityService
        function onChanged() {
            root.syncUploadSelection()
            root.syncProfile()
            if (communityService.authenticated && loginDialog.opened)
                loginDialog.close()
            if (communityService.usernameRequired && !usernameDialog.opened)
                usernameDialog.open()
        }
    }

    Connections {
        target: supporterService
        function onChanged() {
            if (!supporterService.unlocked && jsonService.sourceIndex === 3)
                jsonService.setSource(0)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.px(8)

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.px(root.compactHeight ? 38 : 43)
            Layout.minimumHeight: Layout.preferredHeight
            Layout.maximumHeight: Layout.preferredHeight
            spacing: Theme.px(7)

            Repeater {
                model: [
                    { label: "Browse", icon: "json" },
                    { label: "Upload", icon: "transfer" },
                    { label: "Profile", icon: "heart" }
                ]

                delegate: NavButton {
                    required property var modelData
                    required property int index
                    Layout.preferredWidth: Theme.px(root.compactHeight ? 132 : 148)
                    Layout.preferredHeight: Theme.px(root.compactHeight ? 38 : 43)
                    text: modelData.label
                    iconName: modelData.icon
                    active: root.activeTab === index
                    dense: true
                    toolTipText: index === 0 ? "Browse and download community artwork."
                                              : index === 1 ? "Validate and share one of your JSON files."
                                                            : "Manage your community account and personal views."
                    onClicked: root.activeTab = index
                }
            }

            Item { Layout.fillWidth: true }

            BusyIndicator {
                visible: communityService.busy
                running: visible
                Layout.preferredWidth: Theme.px(24)
                Layout.preferredHeight: Theme.px(24)
                palette.highlight: Theme.primaryBright
            }

            Text {
                Layout.maximumWidth: Theme.px(330)
                text: communityService.statusMessage
                color: communityService.connected ? Theme.muted : Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(9.7)
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideRight
            }

            GhostButton {
                visible: !communityService.authenticated
                dense: true
                iconName: "external"
                text: "Connect"
                toolTipText: communityService.testAuthenticationAvailable
                             ? "Connect a private local test identity to try account features."
                             : "Connect a GitHub identity. KFPS never receives your GitHub password."
                onClicked: root.openLogin()
            }

            GhostButton {
                visible: communityService.authenticated
                dense: true
                iconName: "heart"
                text: communityService.accountLabel
                maximumTextWidth: Theme.px(190)
                toolTipText: "Open your community profile."
                onClicked: root.activeTab = 2
            }

            GhostButton {
                dense: true
                iconName: "refresh"
                text: ""
                minimumWidth: Theme.px(38)
                toolTipText: "Refresh the current community view."
                onClicked: communityService.refresh()
            }
        }

        Rectangle {
            visible: communityService.errorMessage.length > 0
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? Theme.px(42) : 0
            radius: Theme.px(6)
            color: Theme.danger
            opacity: 0.88

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.px(12)
                anchors.rightMargin: Theme.px(7)
                spacing: Theme.px(10)

                Text {
                    Layout.fillWidth: true
                    text: communityService.errorMessage
                    color: "white"
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10.5)
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                GhostButton {
                    dense: true
                    text: "Dismiss"
                    toolTipText: "Dismiss this community error message."
                    onClicked: communityService.clearError()
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.activeTab

            Item {
                GridLayout {
                    anchors.fill: parent
                    columns: root.wide ? 2 : 1
                    columnSpacing: Theme.px(10)
                    rowSpacing: Theme.px(10)

                    GlassPanel {
                        id: browsePanel
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: root.wide ? Theme.px(760) : -1
                        Layout.columnSpan: root.wide && root.supporterCatalogLocked ? 2 : 1
                        strong: true

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.px(root.compactHeight ? 11 : 14)
                            spacing: Theme.px(8)

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(8)
                                visible: !root.supporterCatalogLocked

                                KfpsTextField {
                                    id: searchField
                                    Layout.fillWidth: true
                                    dense: true
                                    text: communityService.searchQuery
                                    placeholderText: "Search titles, tags, or creators"
                                    toolTipText: "Search the current community catalog. Empty the box to show everything."
                                    onTextEdited: communityService.setSearchQuery(text)
                                }

                                KfpsComboBox {
                                    id: categoryFilter
                                    Layout.preferredWidth: Theme.px(145)
                                    dense: true
                                    model: communityService.categories
                                    toolTipText: "Limit results to one artwork category."
                                    onActivated: communityService.setCategory(currentText)
                                }

                                KfpsComboBox {
                                    id: gameFilter
                                    Layout.preferredWidth: Theme.px(92)
                                    dense: true
                                    model: communityService.games
                                    toolTipText: "Show artwork prepared for one Forza game."
                                    onActivated: communityService.setGame(currentText)
                                }

                                KfpsComboBox {
                                    id: sortFilter
                                    Layout.preferredWidth: Theme.px(150)
                                    dense: true
                                    model: communityService.sortOptions
                                    currentIndex: communityService.selectedSortIndex
                                    toolTipText: "Choose how community results are ordered."
                                    onActivated: communityService.setSortIndex(currentIndex)
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(6)

                                Repeater {
                                    model: communityService.scopeOptions

                                    delegate: GhostButton {
                                        required property string modelData
                                        required property int index
                                        dense: true
                                        text: modelData
                                        accentText: communityService.selectedScopeIndex === index
                                        selected: communityService.selectedScopeIndex === index
                                        labelColor: index === 1 ? Theme.classificationHandmade
                                                               : (index === 2 ? Theme.classificationToolmade
                                                                              : (accentText ? Theme.primaryBright : Theme.text))
                                        enabled: index < 4 || communityService.authenticated
                                        toolTipText: index === 0 ? "Show all published community artwork."
                                                      : index === 1 ? "Show only artwork classified as Handmade."
                                                      : index === 2 ? "Show only artwork classified as Toolmade."
                                                      : index === 3 ? (communityService.supporterAccess
                                                                     ? "Show artwork shared only with verified KFPS supporters."
                                                                     : "Open supporter vinyl sharing and access options.")
                                                      : index === 4 ? "Show artwork you marked as a favorite."
                                                      : index === 5 ? "Show artwork from creators you follow."
                                                                    : "Show your uploads and publication status."
                                        onClicked: communityService.setScopeIndex(index)
                                    }
                                }

                                Rectangle {
                                    visible: communityService.creatorFilter.length > 0
                                    Layout.preferredWidth: creatorFilterText.implicitWidth + Theme.px(56)
                                    Layout.preferredHeight: Theme.px(30)
                                    radius: Theme.px(6)
                                    color: Theme.primarySoft
                                    border.width: Math.max(1, Theme.px(1))
                                    border.color: Theme.primary

                                    Text {
                                        id: creatorFilterText
                                        anchors.left: parent.left
                                        anchors.leftMargin: Theme.px(9)
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "@" + communityService.creatorFilter
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(9.8)
                                        font.weight: Font.DemiBold
                                    }

                                    GhostButton {
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: Theme.px(34)
                                        height: Theme.px(28)
                                        dense: true
                                        text: "x"
                                        minimumWidth: Theme.px(30)
                                        toolTipText: "Stop filtering by this creator."
                                        onClicked: communityService.clearCreatorFilter()
                                    }
                                }

                                Item { Layout.fillWidth: true }

                                Text {
                                    visible: !root.supporterCatalogLocked
                                    text: communityService.resultSummary
                                    color: Theme.subtle
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9.6)
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                height: Math.max(1, Theme.px(1))
                                color: Theme.borderSoft
                            }

                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true

                                GridView {
                                    id: artworkGrid
                                    anchors.fill: parent
                                    clip: true
                                    visible: !root.supporterCatalogLocked
                                    model: root.supporterCatalogLocked ? null : communityService.artworkModel
                                    property int columns: width >= Theme.px(790) ? 2 : 1
                                    cellWidth: Math.max(1, width / columns)
                                    cellHeight: Theme.px(root.compactHeight ? 146 : 166)
                                    boundsBehavior: Flickable.StopAtBounds
                                    maximumFlickVelocity: 100000
                                    flickDeceleration: 12000
                                    reuseItems: true
                                    cacheBuffer: height

                                    WheelHandler {
                                        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                                        target: null
                                        onWheel: event => {
                                            var delta = event.pixelDelta.y
                                            if (delta === 0)
                                                delta = (event.angleDelta.y / 120.0) * Theme.px(82)
                                            if (delta === 0)
                                                return

                                            var maximumY = Math.max(0, artworkGrid.contentHeight - artworkGrid.height)
                                            var nextY = Math.max(0, Math.min(
                                                artworkGrid.contentY - delta,
                                                maximumY))
                                            if (nextY !== artworkGrid.contentY) {
                                                artworkGrid.contentY = nextY
                                                event.accepted = true
                                            }
                                        }
                                    }

                                    delegate: CommunityArtworkCard {
                                        required property int index
                                        required property string title
                                        required property string creatorName
                                        required property string previewUrl
                                        required property string thumbnailUrl
                                        required property string category
                                        required property string classificationLabel
                                        required property string gamesText
                                        required property string schemaLabel
                                        required property bool schemaKnown
                                        required property int shapeCount
                                        required property int downloads
                                        required property int favorites
                                        required property bool featured
                                        required property bool supporterOnly
                                        required property string statusLabel

                                        width: artworkGrid.cellWidth - Theme.px(7)
                                        height: artworkGrid.cellHeight - Theme.px(7)
                                        artworkTitle: title
                                        cardCreatorName: creatorName
                                        cardPreviewUrl: thumbnailUrl
                                        cardCategory: category
                                        cardClassificationLabel: classificationLabel
                                        cardGamesText: gamesText
                                        cardSchemaLabel: schemaLabel
                                        cardSchemaKnown: schemaKnown
                                        cardShapeCount: shapeCount
                                        cardDownloads: downloads
                                        cardFavorites: favorites
                                        cardFeatured: featured
                                        cardSupporterOnly: supporterOnly
                                        cardStatusLabel: statusLabel
                                        cardSelected: communityService.selectedIndex === index
                                        onClicked: communityService.selectArtwork(index)
                                        onDoubleClicked: root.openArtworkInspector(index)
                                    }

                                    ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
                                }

                                EmptyState {
                                    visible: !root.supporterCatalogLocked
                                             && communityService.artworkModel.count === 0
                                             && !communityService.busy
                                    anchors.centerIn: parent
                                    iconName: "json"
                                    title: "No matching artwork"
                                    message: "Try another search, filter, or personal view."
                                }

                                Item {
                                    anchors.fill: parent
                                    visible: root.supporterCatalogLocked

                                    Column {
                                        width: Math.min(Theme.px(590), parent.width - Theme.px(48))
                                        anchors.centerIn: parent
                                        spacing: Theme.px(11)

                                        Icon {
                                            name: "heart"
                                            iconSize: Theme.px(root.compactHeight ? 42 : 54)
                                            glow: true
                                            anchors.horizontalCenter: parent.horizontalCenter
                                        }

                                        Text {
                                            width: parent.width
                                            text: !communityService.supporterKeyAvailable
                                                  ? "Get access to supporter vinyl sharing"
                                                  : !root.activeSupporterKey
                                                    ? "Connect your supporter key"
                                                    : !communityService.authenticated
                                                      ? "Connect to the supporter catalog"
                                                      : "Confirming supporter access"
                                            color: Theme.text
                                            font.family: Theme.displayFamily
                                            font.pixelSize: Theme.px(root.compactHeight ? 19 : 23)
                                            font.weight: Font.Bold
                                            horizontalAlignment: Text.AlignHCenter
                                            wrapMode: Text.Wrap
                                        }

                                        Text {
                                            width: parent.width
                                            text: !communityService.supporterKeyAvailable
                                                  ? "Share your best vinyls with other supporters, and browse artwork creators have chosen to keep within the supporter community."
                                                  : !root.activeSupporterKey
                                                    ? "This catalog needs a connected supporter key so access can be verified securely."
                                                    : !communityService.authenticated
                                                      ? "Sign in with GitHub to connect supporter access to your Community profile."
                                                      : "KFPS is checking this supporter registration before loading the private catalog."
                                            color: Theme.muted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(root.compactHeight ? 10.8 : 12)
                                            horizontalAlignment: Text.AlignHCenter
                                            wrapMode: Text.Wrap
                                            lineHeight: 1.08
                                        }

                                        PrimaryButton {
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            iconName: !communityService.supporterKeyAvailable ? "heart" : "external"
                                            showArrow: true
                                            text: !communityService.supporterKeyAvailable
                                                  ? "Get a Supporter Key"
                                                  : !root.activeSupporterKey
                                                    ? "Check Supporter Key"
                                                    : !communityService.authenticated
                                                      ? "Connect Community Account"
                                                      : "Check Supporter Access"
                                            enabled: true
                                            toolTipText: !communityService.supporterKeyAvailable
                                                         ? "Open the KFPS supporter-key page on Ko-fi."
                                                         : !root.activeSupporterKey
                                                           ? "Retry supporter-key activation."
                                                           : !communityService.authenticated
                                                             ? "Connect your GitHub identity to the Community library."
                                                             : "Request a fresh supporter Community verification."
                                            onClicked: {
                                                if (!communityService.supporterKeyAvailable)
                                                    desktop.openUrl("https://ko-fi.com/s/2d1507698d")
                                                else if (!root.activeSupporterKey)
                                                    communityService.repairSupporterAccess()
                                                else if (!communityService.authenticated)
                                                    root.openLogin()
                                                else
                                                    communityService.refreshSupporterEntitlement()
                                            }
                                        }

                                        Text {
                                            width: parent.width
                                            text: !communityService.supporterKeyAvailable
                                                  ? "A supporter key unlocks this catalog and the other KFPS supporter features."
                                                  : !root.activeSupporterKey
                                                    ? communityService.supporterStatus
                                                    : communityService.supporterStatus
                                            color: Theme.subtle
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(9.5)
                                            horizontalAlignment: Text.AlignHCenter
                                            wrapMode: Text.Wrap
                                            maximumLineCount: 2
                                            elide: Text.ElideRight
                                        }
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(8)
                                visible: !root.supporterCatalogLocked

                                GhostButton {
                                    dense: true
                                    iconName: "chevron-right"
                                    text: "Previous"
                                    enabled: communityService.page > 1 && !communityService.busy
                                    toolTipText: "Open the previous catalog page."
                                    onClicked: communityService.previousPage()
                                }

                                Item { Layout.fillWidth: true }

                                Text {
                                    text: "Page " + communityService.page + " of " + communityService.pageCount
                                    color: Theme.muted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(10)
                                }

                                Item { Layout.fillWidth: true }

                                GhostButton {
                                    dense: true
                                    showArrow: true
                                    text: "Next"
                                    enabled: communityService.page < communityService.pageCount && !communityService.busy
                                    toolTipText: "Open the next catalog page."
                                    onClicked: communityService.nextPage()
                                }
                            }
                        }
                    }

                    GlassPanel {
                        id: detailPanel
                        visible: !root.supporterCatalogLocked
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: root.wide ? Theme.px(400) : -1
                        Layout.minimumWidth: root.wide ? Theme.px(340) : 0

                        Item {
                            anchors.fill: parent
                            anchors.margins: Theme.px(root.compactHeight ? 11 : 14)

                            EmptyState {
                                visible: !communityService.hasSelection
                                anchors.centerIn: parent
                                iconName: "json"
                                title: "Choose an artwork"
                                message: "Its preview, creator, details, and download actions will appear here."
                            }

                            ColumnLayout {
                                anchors.fill: parent
                                visible: communityService.hasSelection
                                spacing: Theme.px(8)

                                Rectangle {
                                    objectName: "CommunityDetailPreview"
                                    readonly property bool hovered: detailPreviewHover.hovered
                                    readonly property bool pressed: detailPreviewTap.pressed
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Theme.px(root.compactHeight ? 190 : 250)
                                    radius: Theme.framedRadius(Theme.px(7))
                                    color: detailPreviewHover.hovered ? Theme.fieldHoverSurface : Theme.previewSurface
                                    border.width: Theme.customFrameExclusive
                                                  ? 0
                                                  : Math.max(1, Theme.px(1))
                                    border.color: detailPreviewHover.hovered ? Theme.primary : Theme.borderStrong
                                    clip: true
                                    scale: detailPreviewTap.pressed ? 0.99 : 1.0
                                    Behavior on color { enabled: !Theme.reducedMotion; ColorAnimation { duration: 110 } }
                                    Behavior on scale { enabled: !Theme.reducedMotion; NumberAnimation { duration: 75; easing.type: Easing.OutCubic } }

                                    Image {
                                        id: detailPreview
                                        anchors.fill: parent
                                        anchors.margins: Theme.px(8)
                                        source: String(communityService.selectedArtwork.previewUrl || "")
                                        fillMode: Image.PreserveAspectFit
                                        asynchronous: true
                                        cache: true
                                        smooth: true
                                    }

                                    BusyIndicator {
                                        anchors.centerIn: parent
                                        running: detailPreview.status === Image.Loading
                                        visible: running
                                        palette.highlight: Theme.primaryBright
                                    }

                                    EmptyState {
                                        visible: detailPreview.status === Image.Error
                                                 || !communityService.selectedArtwork.previewUrl
                                        anchors.centerIn: parent
                                        scale: 0.72
                                        iconName: "images"
                                        title: "Preview unavailable"
                                        message: "Refresh the catalog and try again."
                                    }

                                    HoverHandler {
                                        id: detailPreviewHover
                                        cursorShape: Qt.PointingHandCursor
                                    }

                                    TapHandler {
                                        id: detailPreviewTap
                                        onDoubleTapped: root.openArtworkInspector(communityService.selectedIndex)
                                    }

                                    KfpsToolTip {
                                        visible: detailPreviewHover.hovered
                                        text: "Double-click to inspect this preview at a larger size."
                                    }

                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(8)

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.px(2)

                                        Text {
                                            Layout.fillWidth: true
                                            text: String(communityService.selectedArtwork.title || "Untitled")
                                            color: Theme.text
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(16.5)
                                            font.weight: Font.Bold
                                            wrapMode: Text.Wrap
                                            maximumLineCount: 2
                                            elide: Text.ElideRight
                                        }

                                        CommunityClassificationLine {
                                            Layout.fillWidth: true
                                            supporterOnly: Boolean(communityService.selectedArtwork.supporterOnly)
                                            classificationLabel: String(communityService.selectedArtwork.classificationLabel || "Toolmade")
                                            categoryLabel: String(communityService.selectedArtwork.category || "Other")
                                            schemaLabel: String(communityService.selectedArtwork.schemaLabel || "KFPS-compatible JSON")
                                            textPixelSize: Theme.px(9.8)
                                        }
                                    }

                                    Rectangle {
                                        visible: Boolean(communityService.selectedArtwork.featured)
                                        Layout.preferredWidth: Theme.px(72)
                                        Layout.preferredHeight: Theme.px(24)
                                        radius: Theme.px(5)
                                        color: Theme.primarySoft
                                        border.width: Math.max(1, Theme.px(1))
                                        border.color: Theme.primary

                                        Text {
                                            anchors.centerIn: parent
                                            text: "Featured"
                                            color: Theme.primaryBright
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(8.8)
                                            font.weight: Font.Bold
                                        }
                                    }
                                }

                                GhostButton {
                                    Layout.fillWidth: true
                                    dense: true
                                    iconName: "heart"
                                    text: "@" + String(communityService.selectedArtwork.creatorName || "Unknown")
                                          + "  |  " + Number(communityService.selectedArtwork.creatorFollowers || 0) + " followers"
                                    toolTipText: "Open this creator's profile."
                                    onClicked: {
                                        communityService.loadCreator(String(communityService.selectedArtwork.creatorName || ""))
                                        creatorDialog.open()
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(7)

                                    Text {
                                        Layout.fillWidth: true
                                        text: Number(communityService.selectedArtwork.shapeCount || 0).toLocaleString(Qt.locale(), "f", 0) + " shapes"
                                        color: Theme.text
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(10)
                                        font.weight: Font.DemiBold
                                    }

                                    Text {
                                        text: Number(communityService.selectedArtwork.downloads || 0).toLocaleString(Qt.locale(), "f", 0) + " downloads"
                                        color: Theme.muted
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(9.6)
                                    }

                                    Text {
                                        text: Number(communityService.selectedArtwork.favorites || 0).toLocaleString(Qt.locale(), "f", 0) + " favorites"
                                        color: Theme.muted
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(9.6)
                                    }
                                }

                                ScrollView {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.minimumHeight: Theme.px(58)
                                    clip: true
                                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                                    ColumnLayout {
                                        width: parent.width
                                        spacing: Theme.px(6)

                                        Text {
                                            Layout.fillWidth: true
                                            text: String(communityService.selectedArtwork.description || "No description was provided.")
                                            color: Theme.muted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(10.4)
                                            wrapMode: Text.Wrap
                                        }

                                        Text {
                                            visible: String(communityService.selectedArtwork.tagsText || "").length > 0
                                            Layout.fillWidth: true
                                            text: "Tags: " + String(communityService.selectedArtwork.tagsText || "")
                                            color: Theme.subtle
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(9.4)
                                            wrapMode: Text.Wrap
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: String(communityService.selectedArtwork.gamesText || "").length > 0
                                                  ? "Detected game origin: " + String(communityService.selectedArtwork.gamesText)
                                                  : "No game-specific origin was declared by this JSON."
                                            color: Theme.subtle
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(9.2)
                                            wrapMode: Text.Wrap
                                        }

                                        Text {
                                            visible: !Boolean(communityService.selectedArtwork.schemaKnown)
                                            Layout.fillWidth: true
                                            text: String(communityService.selectedArtwork.schemaWarning || "Compatibility is unverified for this JSON format.")
                                            color: Theme.warning
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(9.3)
                                            font.weight: Font.DemiBold
                                            wrapMode: Text.Wrap
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: "License: " + String(communityService.selectedArtwork.license || "kfps-community-share-v1")
                                            color: Theme.subtle
                                            font.family: Theme.monoFamily
                                            font.pixelSize: Theme.px(8.9)
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: "Community upload. Not reviewed against current Forza enforcement rules; download and use at your own risk."
                                            color: Theme.warning
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(9.1)
                                            wrapMode: Text.Wrap
                                        }

                                        Text {
                                            visible: String(communityService.selectedArtwork.statusLabel || "Published") !== "Published"
                                            Layout.fillWidth: true
                                            text: "Status: " + String(communityService.selectedArtwork.statusLabel || "")
                                                  + (String(communityService.selectedArtwork.rejectionReason || "")
                                                     ? " - " + String(communityService.selectedArtwork.rejectionReason) : "")
                                            color: String(communityService.selectedArtwork.statusLabel || "") === "Rejected"
                                                   ? Theme.danger : Theme.warning
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(9.6)
                                            font.weight: Font.DemiBold
                                            wrapMode: Text.Wrap
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(7)

                                    PrimaryButton {
                                        Layout.fillWidth: true
                                        dense: true
                                        iconName: "transfer"
                                        text: communityService.authenticated ? "Download to Library" : "Connect to Download"
                                        enabled: !communityService.busy
                                        toolTipText: communityService.authenticated
                                                     ? "Download, verify, and add this JSON to Outputs > Library."
                                                     : "Connect a Community account before downloading this JSON."
                                        onClicked: communityService.authenticated
                                                   ? communityService.downloadSelected() : root.openLogin()
                                    }

                                    GhostButton {
                                        dense: true
                                        iconName: "heart"
                                        text: Boolean(communityService.selectedArtwork.favorited) ? "Saved" : "Favorite"
                                        enabled: communityService.authenticated && !communityService.busy
                                        toolTipText: communityService.authenticated
                                                     ? "Add or remove this artwork from your favorites."
                                                     : "Connect an account to save favorites."
                                        onClicked: communityService.favoriteSelected()
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(7)

                                    GhostButton {
                                        visible: communityService.downloadedPath.length > 0
                                        dense: true
                                        iconName: "folder"
                                        text: "Open download"
                                        toolTipText: "Open the folder containing the verified downloaded JSON."
                                        onClicked: communityService.openDownloadedFolder()
                                    }

                                    GhostButton {
                                        visible: communityService.authenticated && !communityService.selectedOwned
                                        dense: true
                                        iconName: "reports"
                                        text: "Report"
                                        toolTipText: "Privately flag this artwork for administrator review."
                                        onClicked: reportDialog.open()
                                    }

                                    Item { Layout.fillWidth: true }

                                    GhostButton {
                                        visible: communityService.selectedMetadataEditable
                                        dense: true
                                        text: "Edit tags"
                                        toolTipText: "Change the search tags for this upload. Classification is administrator-managed after publishing."
                                        onClicked: editTagsDialog.open()
                                    }

                                    GhostButton {
                                        visible: communityService.selectedOwned
                                        dense: true
                                        iconName: "transfer"
                                        text: "New revision"
                                        toolTipText: "Prepare a replacement JSON as a new revision of this upload."
                                        onClicked: root.prepareRevision()
                                    }

                                    GhostButton {
                                        visible: communityService.selectedOwned
                                        dense: true
                                        text: "Remove"
                                        toolTipText: "Remove your artwork from the active community catalog."
                                        onClicked: removeDialog.open()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                GridLayout {
                    anchors.fill: parent
                    columns: root.wide ? 2 : 1
                    columnSpacing: Theme.px(10)
                    rowSpacing: Theme.px(10)

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: root.wide ? Theme.px(500) : -1
                        strong: true

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.px(15)
                            spacing: Theme.px(9)

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(10)

                                Icon { name: "json"; iconSize: Theme.px(30); glow: true }
                                SectionHeading {
                                    Layout.fillWidth: true
                                    title: root.revisionMode ? "Revision source" : "Upload source"
                                    subtitle: "KFPS validates the file and renders the public preview locally first."
                                }
                            }

                            GridLayout {
                                Layout.fillWidth: true
                                columns: 3
                                columnSpacing: Theme.px(7)
                                rowSpacing: Theme.px(3)

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(3)

                                    Label { text: "Output folder" }
                                    KfpsComboBox {
                                        id: uploadSource
                                        Layout.fillWidth: true
                                        dense: true
                                        model: supporterService.unlocked
                                               ? ["Generated finals", "Editor exports", "Game exports", "Library"]
                                               : ["Generated finals", "Editor exports", "Game exports"]
                                        currentIndex: Math.min(jsonService.sourceIndex, count - 1)
                                        toolTipText: "Choose which indexed KFPS output folder is shown in the upload browser."
                                        onActivated: {
                                            jsonService.setSource(currentIndex)
                                            uploadFiles.positionViewAtBeginning()
                                        }
                                    }
                                }

                                GhostButton {
                                    Layout.alignment: Qt.AlignBottom
                                    iconName: "folder"
                                    text: "Import JSON File"
                                    dense: true
                                    enabled: !communityService.busy
                                    toolTipText: "Pick any JSON manually in File Explorer without adding it to a KFPS output folder."
                                    onClicked: communityService.chooseUploadJson()
                                }

                                GhostButton {
                                    Layout.alignment: Qt.AlignBottom
                                    iconName: "refresh"
                                    text: "Refresh"
                                    dense: true
                                    toolTipText: "Scan the selected output folder again and update its tiles."
                                    onClicked: jsonService.refresh()
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(8)

                                KfpsTextField {
                                    id: uploadSearch
                                    Layout.fillWidth: true
                                    dense: true
                                    placeholderText: "Search this folder by vinyl name"
                                    toolTipText: "Filter the selected output folder by vinyl name. Empty the box to show every JSON again."
                                    Component.onCompleted: text = jsonService.searchQuery
                                    onTextEdited: {
                                        jsonService.setSearchQuery(text)
                                        uploadFiles.positionViewAtBeginning()
                                    }

                                    Connections {
                                        target: jsonService
                                        function onChanged() {
                                            if (uploadSearch.text !== jsonService.searchQuery)
                                                uploadSearch.text = jsonService.searchQuery
                                        }
                                    }
                                }

                                Text {
                                    Layout.maximumWidth: Theme.px(130)
                                    text: jsonService.searchSummary
                                    color: Theme.subtle
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9.2)
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideRight
                                }
                            }

                            GlassPanel {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.minimumHeight: Theme.px(root.compactHeight ? 210 : 260)
                                soft: true
                                border.color: communityService.uploadPath.length > 0 ? Theme.borderStrong : Theme.borderSoft

                                Item {
                                    anchors.fill: parent
                                    anchors.margins: Theme.px(8)
                                    clip: true

                                    GridView {
                                        id: uploadFiles
                                        anchors.fill: parent
                                        clip: true
                                        model: jsonService.fileModel
                                        boundsBehavior: Flickable.StopAtBounds
                                        maximumFlickVelocity: 100000
                                        flickDeceleration: 12000
                                        property int columns: Math.max(1, Math.floor(width / Theme.px(root.compactHeight ? 138 : 158)))
                                        cellWidth: Math.max(Theme.px(128), width / columns)
                                        cellHeight: Theme.px(root.compactHeight ? 150 : 174)

                                        delegate: CommunityUploadTile {
                                            width: uploadFiles.cellWidth - Theme.px(7)
                                            height: uploadFiles.cellHeight - Theme.px(7)
                                            selected: root.uploadTileSelected(path)
                                            validating: selected && communityService.busy && communityService.uploadPath.length === 0
                                            enabled: !communityService.busy
                                            onClicked: root.prepareUploadPath(path)
                                        }

                                        WheelHandler {
                                            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                                            target: null
                                            onWheel: event => {
                                                var delta = event.pixelDelta.y
                                                if (delta === 0)
                                                    delta = (event.angleDelta.y / 120.0) * Theme.px(96)
                                                if (delta === 0)
                                                    return
                                                uploadFiles.contentY = Math.max(0, Math.min(
                                                    uploadFiles.contentY - delta,
                                                    Math.max(0, uploadFiles.contentHeight - uploadFiles.height)))
                                                event.accepted = true
                                            }
                                        }

                                        ScrollBar.vertical: KfpsScrollBar { policy: ScrollBar.AsNeeded }
                                    }

                                    EmptyState {
                                        visible: uploadFiles.count === 0
                                        anchors.centerIn: parent
                                        iconName: "json"
                                        title: jsonService.currentSourceIndexing
                                               ? "Indexing outputs"
                                               : (jsonService.searchQuery.length > 0 ? "No matching vinyls" : "No JSON files")
                                        message: jsonService.currentSourceIndexing
                                                 ? "Cached tiles will appear as this folder is indexed."
                                                 : (jsonService.searchQuery.length > 0
                                                    ? "No vinyl name in this folder matches the search."
                                                    : "Choose another output folder or import a JSON file manually.")
                                    }
                                }
                            }

                            GlassPanel {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Theme.px(root.compactHeight ? 88 : 104)
                                soft: true
                                border.color: communityService.uploadReady ? Theme.success : Theme.borderSoft

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: Theme.px(8)
                                    spacing: Theme.px(9)

                                    Rectangle {
                                        Layout.preferredWidth: Theme.px(root.compactHeight ? 82 : 100)
                                        Layout.fillHeight: true
                                        radius: Theme.px(6)
                                        color: Theme.previewSurface
                                        border.width: Math.max(1, Theme.px(1))
                                        border.color: Theme.borderSoft
                                        clip: true

                                        Image {
                                            anchors.fill: parent
                                            anchors.margins: Theme.px(4)
                                            source: communityService.uploadPreviewUrl
                                            fillMode: Image.PreserveAspectFit
                                            asynchronous: true
                                            cache: false
                                            smooth: true
                                            mipmap: false
                                        }

                                        EmptyState {
                                            visible: !communityService.uploadPreviewUrl
                                            anchors.centerIn: parent
                                            scale: 0.5
                                            iconName: "json"
                                            title: ""
                                            message: "Select a tile"
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        spacing: Theme.px(2)

                                        Text {
                                            Layout.fillWidth: true
                                            text: communityService.uploadName
                                                  + (communityService.uploadShapeCount > 0
                                                     ? " | " + communityService.uploadShapeCount.toLocaleString(Qt.locale(), "f", 0) + " shapes" : "")
                                            color: Theme.text
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(10.4)
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideMiddle
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: communityService.uploadStatus
                                            color: communityService.uploadPath && !communityService.uploadSchemaKnown
                                                   ? Theme.warning : communityService.uploadReady ? Theme.success : Theme.muted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(9.1)
                                            wrapMode: Text.Wrap
                                            maximumLineCount: 2
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            visible: communityService.uploadPath.length > 0
                                            Layout.fillWidth: true
                                            text: "Detected format: " + communityService.uploadSchemaLabel
                                                  + (communityService.uploadDetectedGamesText.length > 0
                                                     ? " | Origin: " + communityService.uploadDetectedGamesText : "")
                                            color: communityService.uploadSchemaKnown ? Theme.subtle : Theme.warning
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(8.8)
                                            font.weight: Font.DemiBold
                                            maximumLineCount: 1
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            visible: communityService.uploadNormalizationNote.length > 0
                                            Layout.fillWidth: true
                                            text: communityService.uploadNormalizationNote
                                            color: Theme.success
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(8.6)
                                            maximumLineCount: 1
                                            elide: Text.ElideRight
                                        }
                                    }

                                    GhostButton {
                                        visible: root.revisionMode
                                        text: "New upload"
                                        dense: true
                                        toolTipText: "Leave revision mode and publish the prepared file as a separate artwork."
                                        onClicked: {
                                            root.revisionMode = false
                                            root.uploadClassification = ""
                                            root.uploadSupporterOnly = false
                                        }
                                    }
                                }
                            }
                        }
                    }

                    GlassPanel {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.preferredWidth: root.wide ? Theme.px(620) : -1

                        ScrollView {
                            id: uploadScroll
                            anchors.fill: parent
                            anchors.margins: Theme.px(15)
                            clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                            ColumnLayout {
                                width: uploadScroll.availableWidth
                                spacing: Theme.px(9)

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(10)

                                    Icon { name: "transfer"; iconSize: Theme.px(30); glow: true }
                                    SectionHeading {
                                        Layout.fillWidth: true
                                        title: root.revisionMode ? "Publish revision" : "Publish artwork"
                                        subtitle: root.revisionMode
                                                  ? "A valid replacement publishes immediately while the previous revision stays in history."
                                                  : "Valid uploads publish after structure, preview, hash, and duplicate checks."
                                    }
                                }

                                Rectangle {
                                    visible: !communityService.authenticated || communityService.usernameRequired
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Theme.px(72)
                                    radius: Theme.px(6)
                                    color: Theme.primarySoft
                                    border.width: Math.max(1, Theme.px(1))
                                    border.color: Theme.primary

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: Theme.px(10)
                                        spacing: Theme.px(10)

                                        Text {
                                            Layout.fillWidth: true
                                            text: !communityService.authenticated
                                                  ? "Connect an account before uploading. Browsing and previews remain available without one."
                                                  : "Choose your permanent community username before uploading."
                                            color: Theme.text
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(10.4)
                                            wrapMode: Text.Wrap
                                        }

                                        GhostButton {
                                            dense: true
                                            text: communityService.authenticated ? "Choose username" : "Connect"
                                            toolTipText: communityService.authenticated
                                                         ? "Choose the permanent creator name shown with your uploads."
                                                         : "Connect a community account."
                                            onClicked: communityService.authenticated
                                                       ? usernameDialog.open() : root.openLogin()
                                        }
                                    }
                                }

                                Label { text: "Artwork title" }
                                KfpsTextField {
                                    id: uploadTitle
                                    Layout.fillWidth: true
                                    placeholderText: "Public title"
                                    maximumLength: 80
                                    toolTipText: "Name this artwork as other people will see it."
                                }

                                Label { text: "Description" }
                                KfpsTextArea {
                                    id: uploadDescription
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Theme.px(92)
                                    minimumHeight: Theme.px(80)
                                    placeholderText: "What is this design, and is there anything importers should know?"
                                    toolTipText: "Add a short, useful description. Do not include private information or local file paths."
                                }

                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 2
                                    columnSpacing: Theme.px(9)
                                    rowSpacing: Theme.px(5)

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.px(3)
                                        Label { text: "Category" }
                                        KfpsComboBox {
                                            id: uploadCategory
                                            Layout.fillWidth: true
                                            model: communityService.categories
                                            currentIndex: 1
                                            toolTipText: "Choose the single category that best describes this artwork."
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.px(3)
                                        Label { text: "Sharing license" }
                                        KfpsComboBox {
                                            id: uploadLicenseBox
                                            Layout.fillWidth: true
                                            model: ["KFPS Community Share", "CC BY 4.0", "CC BY-NC 4.0", "CC0 1.0"]
                                            toolTipText: "Choose how other people may reuse this upload. Community Share permits in-game use through KFPS."
                                        }
                                    }
                                }

                                Label { text: "Tags" }
                                KfpsTextField {
                                    id: uploadTags
                                    Layout.fillWidth: true
                                    placeholderText: "anime, racing, portrait"
                                    maximumLength: 249
                                    toolTipText: "Add up to ten comma-separated search tags, each no longer than 24 characters."
                                }

                                Label { text: "Classification" }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(8)

                                    GhostButton {
                                        id: handmadeUploadChoice
                                        Layout.fillWidth: true
                                        text: "Handmade"
                                        labelColor: Theme.classificationHandmade
                                        checkable: true
                                        checked: root.uploadClassification === "handmade"
                                        ButtonGroup.group: uploadClassificationGroup
                                        accentText: checked
                                        enabled: !root.revisionMode
                                        toolTipText: root.revisionMode
                                                     ? "Classification is fixed after the first upload."
                                                     : "Choose Handmade for artwork drawn or assembled manually."
                                        onClicked: root.uploadClassification = "handmade"
                                    }

                                    GhostButton {
                                        id: toolmadeUploadChoice
                                        Layout.fillWidth: true
                                        text: "Toolmade"
                                        labelColor: Theme.classificationToolmade
                                        checkable: true
                                        checked: root.uploadClassification === "toolmade"
                                        ButtonGroup.group: uploadClassificationGroup
                                        accentText: checked
                                        enabled: !root.revisionMode
                                        toolTipText: root.revisionMode
                                                     ? "Classification is fixed after the first upload."
                                                     : "Choose Toolmade for artwork generated or converted with a tool."
                                        onClicked: root.uploadClassification = "toolmade"
                                    }
                                }

                                Label { text: "Audience" }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(8)

                                    GhostButton {
                                        id: everyoneUploadChoice
                                        Layout.fillWidth: true
                                        text: "Everyone"
                                        checkable: true
                                        checked: !root.uploadSupporterOnly
                                        ButtonGroup.group: uploadAudienceGroup
                                        accentText: checked
                                        enabled: !root.revisionMode
                                        toolTipText: root.revisionMode
                                                     ? "Audience is fixed after the first upload."
                                                     : "Publish this artwork in the public Community browser."
                                        onClicked: root.uploadSupporterOnly = false
                                    }

                                    GhostButton {
                                        id: supportersUploadChoice
                                        Layout.fillWidth: true
                                        text: "Supporters"
                                        checkable: true
                                        checked: root.uploadSupporterOnly
                                        ButtonGroup.group: uploadAudienceGroup
                                        accentText: checked
                                        enabled: !root.revisionMode && communityService.supporterAccess
                                        toolTipText: root.revisionMode
                                                     ? "Audience is fixed after the first upload."
                                                     : communityService.supporterAccess
                                                       ? "Share this artwork only with currently verified KFPS supporters."
                                                       : communityService.supporterStatus
                                        onClicked: root.uploadSupporterOnly = true
                                    }
                                }

                                ColumnLayout {
                                    visible: communityService.uploadCompatibilityConfirmationRequired
                                    Layout.fillWidth: true
                                    spacing: Theme.px(5)

                                    Text {
                                        Layout.fillWidth: true
                                        text: communityService.uploadSchemaWarning
                                        color: Theme.warning
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.px(9.5)
                                        font.weight: Font.DemiBold
                                        wrapMode: Text.Wrap
                                    }

                                    KfpsCheckBox {
                                        id: compatibilityConfirmation
                                        Layout.fillWidth: true
                                        text: "I understand that this unrecognized format may not import correctly."
                                        toolTipText: "Required only for structurally valid JSON formats KFPS does not currently recognize."
                                    }
                                }

                                ColumnLayout {
                                    visible: root.revisionMode
                                    Layout.fillWidth: true
                                    spacing: Theme.px(3)

                                    Label { text: "Revision note" }
                                    KfpsTextField {
                                        id: revisionNote
                                        Layout.fillWidth: true
                                        placeholderText: "What changed in this revision?"
                                        maximumLength: 240
                                        toolTipText: "Briefly describe the change for the public revision history."
                                    }
                                }

                                KfpsCheckBox {
                                    id: rightsConfirmation
                                    Layout.fillWidth: true
                                    text: "I made this artwork or have permission to share it."
                                    toolTipText: "Required. Do not upload work you are not allowed to distribute or anything containing private data."
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: "KFPS detects the source format and game origin from the file, then sanitizes it into a canonical community JSON. Uploaders and downloaders remain responsible for in-game use."
                                    color: Theme.subtle
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9.2)
                                    wrapMode: Text.Wrap
                                }

                                PrimaryButton {
                                    Layout.fillWidth: true
                                    iconName: "transfer"
                                    text: root.revisionMode ? "Submit Revision" : "Upload Artwork"
                                    enabled: communityService.uploadReady
                                             && uploadTitle.text.trim().length > 0
                                             && uploadCategory.currentIndex > 0
                                             && root.uploadClassification.length > 0
                                             && (!root.uploadSupporterOnly || communityService.supporterAccess)
                                             && rightsConfirmation.checked
                                             && (communityService.uploadSchemaKnown || compatibilityConfirmation.checked)
                                             && (!root.revisionMode || (communityService.selectedOwned && revisionNote.text.trim().length > 0))
                                             && !communityService.busy
                                    toolTipText: root.revisionMode
                                                 ? "Validate and publish this replacement as the selected artwork's next revision."
                                                 : "Validate and publish this artwork to the community catalog."
                                    onClicked: {
                                        if (root.revisionMode) {
                                            communityService.submitRevision(
                                                uploadTitle.text, uploadDescription.text, uploadCategory.currentText,
                                                uploadTags.text, root.uploadClassification, root.uploadLicense(), root.uploadSupporterOnly, rightsConfirmation.checked,
                                                compatibilityConfirmation.checked, revisionNote.text)
                                        } else {
                                            communityService.submitUpload(
                                                uploadTitle.text, uploadDescription.text, uploadCategory.currentText,
                                                uploadTags.text, root.uploadClassification, root.uploadLicense(), root.uploadSupporterOnly, rightsConfirmation.checked,
                                                compatibilityConfirmation.checked)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                Item {
                    anchors.fill: parent

                    EmptyState {
                        visible: !communityService.authenticated
                        anchors.centerIn: parent
                        iconName: "heart"
                        title: "Connect a community account"
                        message: "Connect an account for downloads, uploads, favorites, follows, reports, and creator profiles."
                    }

                    PrimaryButton {
                        visible: !communityService.authenticated
                        anchors.top: parent.verticalCenter
                        anchors.topMargin: Theme.px(92)
                        anchors.horizontalCenter: parent.horizontalCenter
                        iconName: "external"
                        text: "Connect Account"
                        toolTipText: "Connect a local test identity or GitHub identity, depending on the configured service."
                        onClicked: root.openLogin()
                    }

                    GridLayout {
                        visible: communityService.authenticated && !communityService.usernameRequired
                        anchors.fill: parent
                        columns: root.wide ? 2 : 1
                        columnSpacing: Theme.px(10)
                        rowSpacing: Theme.px(10)

                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.preferredWidth: root.wide ? Theme.px(550) : -1
                            strong: true

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: Theme.px(16)
                                spacing: Theme.px(10)

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(12)

                                    Rectangle {
                                        Layout.preferredWidth: Theme.px(64)
                                        Layout.preferredHeight: Theme.px(64)
                                        radius: Theme.px(6)
                                        color: Theme.primarySoft
                                        border.width: Math.max(1, Theme.px(1))
                                        border.color: Theme.primary
                                        clip: true

                                        Image {
                                            anchors.fill: parent
                                            source: String(communityService.sessionUser.avatar_url || "")
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            visible: source.toString().length > 0
                                        }

                                        Text {
                                            anchors.centerIn: parent
                                            visible: !parent.children[0].visible
                                            text: communityService.username ? communityService.username.charAt(0).toUpperCase() : "?"
                                            color: Theme.primaryBright
                                            font.family: Theme.displayFamily
                                            font.pixelSize: Theme.px(27)
                                            font.weight: Font.Bold
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.px(2)

                                        Text {
                                            Layout.fillWidth: true
                                            text: "@" + communityService.username
                                            color: Theme.text
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(20)
                                            font.weight: Font.Bold
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: String(communityService.sessionUser.provider || "") === "github"
                                                  ? "GitHub @" + String(communityService.sessionUser.provider_login || "")
                                                    + " | permanent community username"
                                                  : "Local test identity | permanent community username"
                                            color: Theme.subtle
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(9.7)
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: communityService.supporterStatus
                                            color: communityService.supporterAccess ? Theme.success : Theme.muted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(9.4)
                                            font.weight: communityService.supporterAccess ? Font.DemiBold : Font.Normal
                                            elide: Text.ElideRight
                                        }
                                    }

                                    GhostButton {
                                        dense: true
                                        text: "Sign out"
                                        toolTipText: "Remove the protected community session from this Windows account."
                                        onClicked: {
                                            root.profileLoadedFor = ""
                                            communityService.signOut()
                                        }
                                    }
                                }

                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 4
                                    columnSpacing: Theme.px(8)
                                    rowSpacing: Theme.px(4)

                                    Repeater {
                                        model: [
                                            { label: "Uploads", value: Number(communityService.sessionStats.artwork_count || 0) },
                                            { label: "Favorites", value: Number(communityService.sessionStats.favorite_count || 0) },
                                            { label: "Following", value: Number(communityService.sessionStats.following_count || 0) },
                                            { label: "Followers", value: Number(communityService.sessionStats.follower_count || 0) }
                                        ]

                                        delegate: Rectangle {
                                            required property var modelData
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: Theme.px(58)
                                            radius: Theme.px(6)
                                            color: Theme.surfaceSoft
                                            border.width: Math.max(1, Theme.px(1))
                                            border.color: Theme.borderSoft

                                            Column {
                                                anchors.centerIn: parent
                                                spacing: Theme.px(2)

                                                Text {
                                                    anchors.horizontalCenter: parent.horizontalCenter
                                                    text: modelData.value.toLocaleString(Qt.locale(), "f", 0)
                                                    color: Theme.primaryBright
                                                    font.family: Theme.fontFamily
                                                    font.pixelSize: Theme.px(15)
                                                    font.weight: Font.Bold
                                                }

                                                Text {
                                                    anchors.horizontalCenter: parent.horizontalCenter
                                                    text: modelData.label
                                                    color: Theme.muted
                                                    font.family: Theme.fontFamily
                                                    font.pixelSize: Theme.px(8.8)
                                                }
                                            }
                                        }
                                    }
                                }

                                Label { text: "Profile bio" }
                                KfpsTextArea {
                                    id: profileBio
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Theme.px(150)
                                    Layout.minimumHeight: Theme.px(120)
                                    placeholderText: "A short public creator bio"
                                    toolTipText: "Write up to 280 characters shown on your public creator profile."
                                }

                                Label { text: "Website" }
                                KfpsTextField {
                                    id: profileWebsite
                                    Layout.fillWidth: true
                                    placeholderText: "https://example.com"
                                    toolTipText: "Optional public HTTPS website for your creator profile."
                                }

                                PrimaryButton {
                                    Layout.fillWidth: true
                                    iconName: "check"
                                    text: "Save Profile"
                                    enabled: !communityService.busy
                                    toolTipText: "Save your public bio and website. Your username cannot be changed."
                                    onClicked: communityService.updateProfile(profileBio.text, profileWebsite.text)
                                }

                                Item { Layout.fillHeight: true }
                            }
                        }

                        GlassPanel {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.preferredWidth: root.wide ? Theme.px(520) : -1

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: Theme.px(16)
                                spacing: Theme.px(10)

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(10)
                                    Icon { name: "json"; iconSize: Theme.px(30); glow: true }
                                    SectionHeading {
                                        Layout.fillWidth: true
                                        title: "Your library activity"
                                        subtitle: "Jump directly to uploads, saved artwork, or followed creators."
                                    }
                                }

                                PrimaryButton {
                                    Layout.fillWidth: true
                                    iconName: "transfer"
                                    text: "My Uploads"
                                    toolTipText: "Browse your uploads and their publication status."
                                    onClicked: {
                                        root.activeTab = 0
                                        communityService.setScopeIndex(6)
                                    }
                                }

                                GhostButton {
                                    Layout.fillWidth: true
                                    iconName: "heart"
                                    text: "Favorites"
                                    toolTipText: "Browse artwork you saved as a favorite."
                                    onClicked: {
                                        root.activeTab = 0
                                        communityService.setScopeIndex(4)
                                    }
                                }

                                GhostButton {
                                    Layout.fillWidth: true
                                    iconName: "heart"
                                    text: "Following"
                                    toolTipText: "Browse recent artwork from creators you follow."
                                    onClicked: {
                                        root.activeTab = 0
                                        communityService.setScopeIndex(5)
                                    }
                                }

                                GhostButton {
                                    Layout.fillWidth: true
                                    iconName: "folder"
                                    text: "Community Downloads"
                                    toolTipText: "Open the local folder where verified community JSON files are saved."
                                    onClicked: communityService.openDownloadedFolder()
                                }

                                Item { Layout.fillHeight: true }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Theme.px(120)
                                    radius: Theme.px(6)
                                    color: Theme.surfaceSoft
                                    border.width: Math.max(1, Theme.px(1))
                                    border.color: Theme.borderSoft

                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: Theme.px(12)
                                        spacing: Theme.px(5)

                                        Text {
                                            Layout.fillWidth: true
                                            text: "Account privacy"
                                            color: Theme.primaryBright
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(11.2)
                                            font.weight: Font.Bold
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: "The community session is encrypted for this Windows user. Supporter keys and receipts are not read or sent by this feature."
                                            color: Theme.muted
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.px(9.7)
                                            wrapMode: Text.Wrap
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            text: communityService.serviceUrl
                                            color: Theme.subtle
                                            font.family: Theme.monoFamily
                                            font.pixelSize: Theme.px(8.8)
                                            elide: Text.ElideMiddle
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: loginDialog
        modal: true
        focus: true
        dim: true
        closePolicy: communityService.authenticationInProgress
                     ? Popup.NoAutoClose : Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Math.min(root.width - Theme.px(48), Theme.px(610))
        height: Theme.px(communityService.authenticationInProgress
                         || (communityService.githubAuthenticationAvailable && communityService.testAuthenticationAvailable)
                         ? 500 : 370)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(20)

        background: Rectangle {
            radius: Theme.framedRadius(Theme.px(8))
            color: Theme.surfaceRaised
            border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
            border.color: Theme.borderStrong
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(12)

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(11)
                Icon { name: "external"; iconSize: Theme.px(34); glow: true }
                SectionHeading {
                    Layout.fillWidth: true
                    title: "Connect a community account"
                    subtitle: "Browsing and previews work without an account."
                }
                GhostButton {
                    visible: !communityService.authenticationInProgress
                    dense: true
                    text: "x"
                    minimumWidth: Theme.px(36)
                    toolTipText: "Close community sign-in."
                    onClicked: loginDialog.close()
                }
            }

            Rectangle {
                visible: communityService.errorMessage.length > 0
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? Theme.px(44) : 0
                radius: Theme.px(6)
                color: Theme.surfaceSoft
                border.width: Math.max(1, Theme.px(1))
                border.color: Theme.danger

                Text {
                    anchors.fill: parent
                    anchors.margins: Theme.px(9)
                    text: communityService.errorMessage
                    color: Theme.danger
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(9.8)
                    wrapMode: Text.Wrap
                    verticalAlignment: Text.AlignVCenter
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: communityService.authenticationInProgress ? 1 : 0

                ColumnLayout {
                    spacing: Theme.px(11)

                    Rectangle {
                        visible: communityService.githubAuthenticationAvailable
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(138)
                        radius: Theme.px(7)
                        color: Theme.surfaceSoft
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.borderSoft

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.px(13)
                            spacing: Theme.px(7)
                            Text {
                                Layout.fillWidth: true
                                text: "GitHub"
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(13)
                                font.weight: Font.Bold
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "Use your public GitHub identity. KFPS never receives your password or requests repository access."
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(10)
                                wrapMode: Text.Wrap
                            }
                            Item { Layout.fillHeight: true }
                            PrimaryButton {
                                Layout.fillWidth: true
                                iconName: "external"
                                text: "Continue with GitHub"
                                toolTipText: "Start GitHub Device Flow in your default browser."
                                onClicked: communityService.connectAccountWith("github")
                            }
                        }
                    }

                    Rectangle {
                        visible: communityService.testAuthenticationAvailable
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(126)
                        radius: Theme.px(7)
                        color: Theme.surfaceSoft
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.borderSoft

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.px(13)
                            spacing: Theme.px(7)
                            Text {
                                Layout.fillWidth: true
                                text: "Local test account"
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(12.3)
                                font.weight: Font.Bold
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "Creates a disposable identity in the local test database. It is never available on the public service."
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(9.8)
                                wrapMode: Text.Wrap
                            }
                            Item { Layout.fillHeight: true }
                            GhostButton {
                                Layout.fillWidth: true
                                iconName: "terminal"
                                text: "Use Local Test Account"
                                toolTipText: "Connect this Windows installation to the local community test database."
                                onClicked: communityService.connectAccountWith("local-test")
                            }
                        }
                    }

                    EmptyState {
                        visible: !communityService.githubAuthenticationAvailable
                                 && !communityService.testAuthenticationAvailable
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        iconName: "external"
                        title: "Sign-in is not configured"
                        message: "The community service is online, but it has no GitHub client ID. Browsing and previews remain available."
                    }

                    Item { Layout.fillHeight: true }

                    Text {
                        Layout.fillWidth: true
                        text: "Community sessions are encrypted for this Windows user and stay separate from supporter activation."
                        color: Theme.subtle
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(9.2)
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                    }
                }

                ColumnLayout {
                    spacing: Theme.px(12)

                    BusyIndicator {
                        visible: !communityService.githubAuthorizationReady
                        running: visible
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: Theme.px(42)
                        Layout.preferredHeight: Theme.px(42)
                        palette.highlight: Theme.primaryBright
                    }

                    Text {
                        Layout.fillWidth: true
                        text: communityService.authenticationProvider === "github"
                              ? (communityService.githubAuthorizationReady
                                 ? "Enter this one-time code on GitHub"
                                 : "Requesting a one-time code from GitHub...")
                              : "Connecting the local test account..."
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(14)
                        font.weight: Font.Bold
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                    }

                    Rectangle {
                        visible: communityService.githubAuthorizationReady
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.px(112)
                        radius: Theme.px(7)
                        color: Theme.previewSurface
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.primary

                        ColumnLayout {
                            anchors.centerIn: parent
                            spacing: Theme.px(5)
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: communityService.githubUserCode
                                color: Theme.primaryBright
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.px(28)
                                font.weight: Font.Bold
                            }
                            Text {
                                Layout.alignment: Qt.AlignHCenter
                                text: "Expires in " + Math.floor(communityService.githubCodeSecondsRemaining / 60)
                                      + ":" + String(communityService.githubCodeSecondsRemaining % 60).padStart(2, "0")
                                color: Theme.muted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(9.6)
                            }
                        }
                    }

                    Text {
                        visible: communityService.githubAuthorizationReady
                        Layout.fillWidth: true
                        text: "The browser page may already be open. Paste the code, approve the public identity request, then return to KFPS."
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(10.2)
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                    }

                    RowLayout {
                        visible: communityService.githubAuthorizationReady
                        Layout.fillWidth: true
                        spacing: Theme.px(8)

                        GhostButton {
                            Layout.fillWidth: true
                            iconName: "json"
                            text: "Copy Code"
                            toolTipText: "Copy the one-time GitHub code to the clipboard."
                            onClicked: communityService.copyGithubCode()
                        }

                        PrimaryButton {
                            Layout.fillWidth: true
                            iconName: "external"
                            text: "Open GitHub"
                            toolTipText: "Open GitHub's verified Device Flow page in your default browser."
                            onClicked: communityService.openGithubVerification()
                        }
                    }

                    Item { Layout.fillHeight: true }

                    GhostButton {
                        visible: communityService.authenticationProvider === "github"
                        Layout.alignment: Qt.AlignHCenter
                        text: "Cancel Sign-In"
                        toolTipText: "Cancel this one-time GitHub sign-in attempt."
                        onClicked: communityService.cancelAuthentication()
                    }
                }
            }
        }
    }

    Popup {
        id: artworkInspector
        property real previewZoom: 1.0

        function moveSelection(offset) {
            communityService.selectRelativeArtwork(offset)
            previewZoom = 1.0
            previewFlick.contentX = 0
            previewFlick.contentY = 0
        }

        modal: true
        focus: true
        dim: true
        closePolicy: Popup.CloseOnEscape
        width: Math.min(root.width - Theme.px(28), Theme.px(1460))
        height: root.height - Theme.px(24)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(14)
        onClosed: previewZoom = 1.0

        background: Rectangle {
            radius: Theme.framedRadius(Theme.px(8))
            color: Theme.surfaceRaised
            border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
            border.color: Theme.borderStrong
        }

        contentItem: ColumnLayout {
            focus: true
            spacing: Theme.px(10)

            Keys.onPressed: event => {
                if (event.key === Qt.Key_Left && communityService.canSelectPrevious) {
                    artworkInspector.moveSelection(-1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Right && communityService.canSelectNext) {
                    artworkInspector.moveSelection(1)
                    event.accepted = true
                } else if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal) {
                    artworkInspector.previewZoom = Math.min(4.0, artworkInspector.previewZoom + 0.25)
                    event.accepted = true
                } else if (event.key === Qt.Key_Minus) {
                    artworkInspector.previewZoom = Math.max(1.0, artworkInspector.previewZoom - 0.25)
                    event.accepted = true
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(8)

                GhostButton {
                    dense: true
                    text: "Previous"
                    enabled: communityService.canSelectPrevious
                    toolTipText: "Inspect the previous artwork on this catalog page."
                    onClicked: artworkInspector.moveSelection(-1)
                }

                Text {
                    text: (communityService.selectedIndex + 1) + " of " + communityService.pageItemCount
                    color: Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(9.8)
                }

                GhostButton {
                    dense: true
                    text: "Next"
                    enabled: communityService.canSelectNext
                    toolTipText: "Inspect the next artwork on this catalog page."
                    onClicked: artworkInspector.moveSelection(1)
                }

                Item { Layout.fillWidth: true }

                Text {
                    Layout.maximumWidth: Theme.px(540)
                    text: String(communityService.selectedArtwork.title || "Untitled")
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(14.5)
                    font.weight: Font.Bold
                    elide: Text.ElideRight
                }

                Item { Layout.fillWidth: true }

                GhostButton {
                    dense: true
                    text: "-"
                    minimumWidth: Theme.px(36)
                    enabled: artworkInspector.previewZoom > 1.0
                    toolTipText: "Zoom out."
                    onClicked: artworkInspector.previewZoom = Math.max(1.0, artworkInspector.previewZoom - 0.25)
                }

                GhostButton {
                    dense: true
                    text: Math.round(artworkInspector.previewZoom * 100) + "%"
                    minimumWidth: Theme.px(62)
                    toolTipText: "Reset the preview to fit the window."
                    onClicked: {
                        artworkInspector.previewZoom = 1.0
                        previewFlick.contentX = 0
                        previewFlick.contentY = 0
                    }
                }

                GhostButton {
                    dense: true
                    text: "+"
                    minimumWidth: Theme.px(36)
                    enabled: artworkInspector.previewZoom < 4.0
                    toolTipText: "Zoom in."
                    onClicked: artworkInspector.previewZoom = Math.min(4.0, artworkInspector.previewZoom + 0.25)
                }

                GhostButton {
                    dense: true
                    text: "x"
                    minimumWidth: Theme.px(36)
                    toolTipText: "Close the large artwork preview."
                    onClicked: artworkInspector.close()
                }
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                columns: artworkInspector.width >= Theme.px(1050) ? 2 : 1
                columnSpacing: Theme.px(12)
                rowSpacing: Theme.px(10)

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: Theme.px(880)
                    Layout.minimumHeight: Theme.px(360)
                    radius: Theme.px(7)
                    color: Theme.previewSurface
                    border.width: Math.max(1, Theme.px(1))
                    border.color: Theme.borderStrong
                    clip: true

                    Flickable {
                        id: previewFlick
                        anchors.fill: parent
                        anchors.margins: Theme.px(5)
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        contentWidth: width * artworkInspector.previewZoom
                        contentHeight: height * artworkInspector.previewZoom

                        Item {
                            width: previewFlick.contentWidth
                            height: previewFlick.contentHeight

                            Image {
                                id: inspectorImage
                                anchors.fill: parent
                                anchors.margins: Theme.px(8)
                                source: String(communityService.selectedArtwork.previewUrl || "")
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                                cache: true
                                smooth: true
                            }
                        }

                        ScrollBar.vertical: KfpsScrollBar { policy: artworkInspector.previewZoom > 1 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
                        ScrollBar.horizontal: ScrollBar { policy: artworkInspector.previewZoom > 1 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
                    }

                    BusyIndicator {
                        anchors.centerIn: parent
                        running: inspectorImage.status === Image.Loading
                        visible: running
                        palette.highlight: Theme.primaryBright
                    }

                    EmptyState {
                        visible: inspectorImage.status === Image.Error || !communityService.selectedArtwork.previewUrl
                        anchors.centerIn: parent
                        iconName: "images"
                        title: "Preview unavailable"
                        message: "Refresh the catalog and try again."
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: Theme.px(390)
                    radius: Theme.px(7)
                    color: Theme.surfaceSoft
                    border.width: Math.max(1, Theme.px(1))
                    border.color: Theme.borderSoft

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.px(14)
                        spacing: Theme.px(9)

                        Text {
                            Layout.fillWidth: true
                            text: String(communityService.selectedArtwork.title || "Untitled")
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(17)
                            font.weight: Font.Bold
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }

                        GhostButton {
                            Layout.fillWidth: true
                            iconName: "heart"
                            text: "@" + String(communityService.selectedArtwork.creatorName || "Unknown")
                            toolTipText: "Open this creator's profile."
                            onClicked: {
                                communityService.loadCreator(String(communityService.selectedArtwork.creatorName || ""))
                                artworkInspector.close()
                                creatorDialog.open()
                            }
                        }

                        CommunityClassificationLine {
                            Layout.fillWidth: true
                            supporterOnly: Boolean(communityService.selectedArtwork.supporterOnly)
                            classificationLabel: String(communityService.selectedArtwork.classificationLabel || "Toolmade")
                            categoryLabel: String(communityService.selectedArtwork.category || "Other")
                            schemaLabel: String(communityService.selectedArtwork.schemaLabel || "KFPS-compatible JSON")
                            textPixelSize: Theme.px(9.8)
                        }

                        Text {
                            Layout.fillWidth: true
                            text: Number(communityService.selectedArtwork.shapeCount || 0).toLocaleString(Qt.locale(), "f", 0)
                                  + " shapes  |  "
                                  + Number(communityService.selectedArtwork.downloads || 0).toLocaleString(Qt.locale(), "f", 0)
                                  + " downloads  |  "
                                  + Number(communityService.selectedArtwork.favorites || 0).toLocaleString(Qt.locale(), "f", 0)
                                  + " favorites"
                            color: Theme.subtle
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(9.2)
                            wrapMode: Text.Wrap
                        }

                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                            ColumnLayout {
                                width: parent.width
                                spacing: Theme.px(8)
                                Text {
                                    Layout.fillWidth: true
                                    text: String(communityService.selectedArtwork.description || "No description was provided.")
                                    color: Theme.text
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(10.4)
                                    wrapMode: Text.Wrap
                                }
                                Text {
                                    visible: String(communityService.selectedArtwork.tagsText || "").length > 0
                                    Layout.fillWidth: true
                                    text: "Tags: " + String(communityService.selectedArtwork.tagsText || "")
                                    color: Theme.muted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9.5)
                                    wrapMode: Text.Wrap
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: "License: " + String(communityService.selectedArtwork.license || "kfps-community-share-v1")
                                    color: Theme.subtle
                                    font.family: Theme.monoFamily
                                    font.pixelSize: Theme.px(8.8)
                                    wrapMode: Text.Wrap
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: String(communityService.selectedArtwork.gamesText || "").length > 0
                                          ? "Detected game origin: " + String(communityService.selectedArtwork.gamesText)
                                          : "No game-specific origin was declared by this JSON."
                                    color: Theme.subtle
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9.2)
                                    wrapMode: Text.Wrap
                                }
                                Text {
                                    visible: !Boolean(communityService.selectedArtwork.schemaKnown)
                                    Layout.fillWidth: true
                                    text: String(communityService.selectedArtwork.schemaWarning || "Compatibility is unverified for this JSON format.")
                                    color: Theme.warning
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9.3)
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.Wrap
                                }
                            }
                        }

                        Text {
                            visible: communityService.errorMessage.length > 0
                            Layout.fillWidth: true
                            text: communityService.errorMessage
                            color: Theme.danger
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(9.4)
                            wrapMode: Text.Wrap
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Theme.px(66)
                            radius: Theme.px(6)
                            color: Theme.surfaceRaised
                            border.width: Math.max(1, Theme.px(1))
                            border.color: Theme.warning

                            Text {
                                anchors.fill: parent
                                anchors.margins: Theme.px(9)
                                text: "Community content is not reviewed against current Forza enforcement rules. Download, import, and use it at your own risk."
                                color: Theme.warning
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(9.4)
                                wrapMode: Text.Wrap
                                verticalAlignment: Text.AlignVCenter
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(7)
                            PrimaryButton {
                                Layout.fillWidth: true
                                dense: true
                                iconName: "transfer"
                                text: communityService.authenticated ? "Download to Library" : "Connect to Download"
                                enabled: !communityService.busy
                                toolTipText: communityService.authenticated
                                             ? "Download and verify this JSON, accepting responsibility for its in-game use."
                                             : "Connect a Community account before downloading this JSON."
                                onClicked: communityService.authenticated
                                           ? communityService.downloadSelected() : root.openLogin()
                            }
                            GhostButton {
                                dense: true
                                iconName: "heart"
                                text: Boolean(communityService.selectedArtwork.favorited) ? "Saved" : "Favorite"
                                enabled: communityService.authenticated && !communityService.busy
                                toolTipText: communityService.authenticated
                                             ? "Add or remove this artwork from your favorites."
                                             : "Connect an account to save favorites."
                                onClicked: communityService.favoriteSelected()
                            }
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: usernameDialog
        modal: true
        focus: true
        dim: true
        closePolicy: Popup.NoAutoClose
        width: Math.min(root.width - Theme.px(48), Theme.px(560))
        height: Theme.px(390)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(18)

        background: Rectangle {
            radius: Theme.framedRadius(Theme.px(8))
            color: Theme.surfaceRaised
            border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
            border.color: Theme.borderStrong
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(12)

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(10)
                Icon { name: "heart"; iconSize: Theme.px(34); glow: true }
                SectionHeading {
                    Layout.fillWidth: true
                    title: "Choose your community username"
                    subtitle: "This public creator name can only be chosen once."
                }
            }

            Text {
                Layout.fillWidth: true
                text: "Use 3-24 letters, numbers, or underscores. Choose carefully: spelling and capitalization are permanent after the server accepts it."
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(11)
                wrapMode: Text.Wrap
            }

            Label { text: "Permanent username" }
            KfpsTextField {
                id: usernameField
                Layout.fillWidth: true
                placeholderText: "CreatorName"
                maximumLength: 24
                validator: RegularExpressionValidator { regularExpression: /^[A-Za-z0-9_]{3,24}$/ }
                toolTipText: "Enter 3-24 letters, numbers, or underscores. This cannot be changed later."
            }

            Text {
                visible: communityService.errorMessage.length > 0
                Layout.fillWidth: true
                text: communityService.errorMessage
                color: Theme.danger
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(9.7)
                wrapMode: Text.Wrap
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.px(48)
                radius: Theme.px(6)
                color: Theme.primarySoft

                Text {
                    anchors.fill: parent
                    anchors.margins: Theme.px(9)
                    text: "KFPS checks usernames case-insensitively, blocks reserved names, and prevents duplicate claims."
                    color: Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(9.6)
                    wrapMode: Text.Wrap
                }
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(8)

                GhostButton {
                    text: "Sign out"
                    toolTipText: "Cancel setup by removing this community session from the computer."
                    onClicked: {
                        usernameDialog.close()
                        communityService.signOut()
                    }
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "Review Username"
                    iconName: "check"
                    enabled: usernameField.acceptableInput && !communityService.busy
                    toolTipText: "Review the exact spelling and capitalization before the final permanent confirmation."
                    onClicked: {
                        root.pendingCommunityUsername = usernameField.text.trim()
                        communityService.clearError()
                        usernameConfirmDialog.open()
                    }
                }
            }
        }

        Connections {
            target: communityService
            function onChanged() {
                if (!communityService.usernameRequired && usernameDialog.opened)
                    usernameDialog.close()
            }
        }
    }

    Popup {
        id: usernameConfirmDialog
        modal: true
        focus: true
        dim: true
        z: 20
        closePolicy: Popup.NoAutoClose
        width: Math.min(root.width - Theme.px(48), Theme.px(560))
        height: Theme.px(350)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(18)

        background: Rectangle {
            radius: Theme.framedRadius(Theme.px(8))
            color: Theme.surfaceRaised
            border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
            border.color: Theme.warning
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(12)

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(10)
                Icon { name: "check"; iconSize: Theme.px(34); glow: true }
                SectionHeading {
                    Layout.fillWidth: true
                    title: "Confirm permanent username"
                    subtitle: "Second and final confirmation"
                }
            }

            Text {
                Layout.fillWidth: true
                text: "Check the exact spelling and capitalization. After the server accepts this name, it cannot be edited or replaced."
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(10.8)
                wrapMode: Text.Wrap
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.px(72)
                radius: Theme.px(6)
                color: Theme.previewSurface
                border.width: Math.max(1, Theme.px(1))
                border.color: Theme.primary

                Text {
                    anchors.fill: parent
                    anchors.margins: Theme.px(10)
                    text: "@" + root.pendingCommunityUsername
                    color: Theme.primaryBright
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.px(20)
                    font.weight: Font.Bold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
            }

            Text {
                Layout.fillWidth: true
                text: "Choose Back to edit it. Confirm Permanently sends this exact name to the Community service."
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(9.7)
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(8)

                GhostButton {
                    text: "Back"
                    toolTipText: "Return to the username field without claiming this name."
                    onClicked: usernameConfirmDialog.close()
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    text: "Confirm Permanently"
                    iconName: "check"
                    enabled: root.pendingCommunityUsername.length >= 3
                             && root.pendingCommunityUsername.length <= 24
                             && !communityService.busy
                    toolTipText: "Permanently claim the exact username shown above."
                    onClicked: {
                        var confirmed = root.pendingCommunityUsername
                        usernameConfirmDialog.close()
                        communityService.chooseUsername(confirmed, confirmed)
                    }
                }
            }
        }
    }

    Popup {
        id: creatorDialog
        modal: true
        focus: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Math.min(root.width - Theme.px(48), Theme.px(620))
        height: Theme.px(440)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(18)

        background: Rectangle {
            radius: Theme.framedRadius(Theme.px(8))
            color: Theme.surfaceRaised
            border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
            border.color: Theme.borderStrong
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(12)

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(12)

                Rectangle {
                    Layout.preferredWidth: Theme.px(74)
                    Layout.preferredHeight: Theme.px(74)
                    radius: Theme.px(6)
                    color: Theme.primarySoft
                    border.width: Math.max(1, Theme.px(1))
                    border.color: Theme.primary
                    clip: true

                    Image {
                        anchors.fill: parent
                        source: String(communityService.creatorProfile.avatar_url || "")
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                    }

                    Text {
                        anchors.centerIn: parent
                        visible: !parent.children[0].source
                        text: String(communityService.creatorProfile.username || "?").charAt(0).toUpperCase()
                        color: Theme.primaryBright
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.px(30)
                        font.weight: Font.Bold
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(3)

                    Text {
                        Layout.fillWidth: true
                        text: communityService.creatorProfile.username
                              ? "@" + String(communityService.creatorProfile.username) : "Loading creator..."
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(21)
                        font.weight: Font.Bold
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        text: Number(communityService.creatorProfile.artwork_count || 0) + " artworks | "
                              + Number(communityService.creatorProfile.downloads || 0) + " downloads | "
                              + Number(communityService.creatorProfile.followers || 0) + " followers"
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(10.2)
                        elide: Text.ElideRight
                    }
                }

                GhostButton {
                    dense: true
                    text: "Close"
                    toolTipText: "Close this creator profile."
                    onClicked: creatorDialog.close()
                }
            }

            Rectangle { Layout.fillWidth: true; height: Math.max(1, Theme.px(1)); color: Theme.borderSoft }

            Text {
                Layout.fillWidth: true
                Layout.fillHeight: true
                text: String(communityService.creatorProfile.bio || "This creator has not added a bio yet.")
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(11.2)
                wrapMode: Text.Wrap
                verticalAlignment: Text.AlignTop
            }

            GhostButton {
                visible: String(communityService.creatorProfile.website_url || "").length > 0
                Layout.fillWidth: true
                iconName: "external"
                text: String(communityService.creatorProfile.website_url || "")
                maximumTextWidth: Theme.px(460)
                toolTipText: "Open this creator's external website in your default browser."
                onClicked: desktop.openUrl(String(communityService.creatorProfile.website_url || ""))
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(8)

                GhostButton {
                    visible: communityService.authenticated && !Boolean(communityService.creatorProfile.is_me)
                    iconName: "heart"
                    text: Boolean(communityService.creatorProfile.followed) ? "Following" : "Follow Creator"
                    toolTipText: "Follow or unfollow this creator."
                    onClicked: communityService.followSelectedCreator()
                }

                Item { Layout.fillWidth: true }

                PrimaryButton {
                    showArrow: true
                    text: "View Artwork"
                    enabled: String(communityService.creatorProfile.username || "").length > 0
                    toolTipText: "Close this profile and filter the catalog to this creator."
                    onClicked: {
                        communityService.browseCreator(String(communityService.creatorProfile.username || ""))
                        root.activeTab = 0
                        creatorDialog.close()
                    }
                }
            }
        }
    }

    Popup {
        id: editTagsDialog
        objectName: "CommunityEditTagsDialog"
        modal: true
        focus: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Math.min(root.width - Theme.px(48), Theme.px(520))
        height: Theme.px(260)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(18)
        onAboutToShow: editTagsField.text = String(communityService.selectedArtwork.tagsText || "")

        background: Rectangle {
            radius: Theme.framedRadius(Theme.px(8))
            color: Theme.surfaceRaised
            border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
            border.color: Theme.borderStrong
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(10)

            SectionHeading {
                Layout.fillWidth: true
                title: "Edit upload tags"
                subtitle: String(communityService.selectedArtwork.title || "Selected upload")
            }

            Label { text: "Tags" }
            KfpsTextField {
                id: editTagsField
                Layout.fillWidth: true
                placeholderText: "anime, racing, portrait"
                maximumLength: 249
                toolTipText: "Add up to ten comma-separated search tags, each no longer than 24 characters."
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(8)
                GhostButton {
                    text: "Cancel"
                    toolTipText: "Close without changing the upload tags."
                    onClicked: editTagsDialog.close()
                }
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    text: "Save Tags"
                    iconName: "check"
                    enabled: communityService.selectedMetadataEditable && !communityService.busy
                    toolTipText: "Save these search tags without changing the uploaded JSON or its classification."
                    onClicked: {
                        communityService.updateSelectedTags(editTagsField.text)
                        editTagsDialog.close()
                    }
                }
            }
        }
    }

    Popup {
        id: reportDialog
        modal: true
        focus: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Math.min(root.width - Theme.px(48), Theme.px(560))
        height: Theme.px(420)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(18)

        function reasonCode() {
            return ["copyright", "misleading", "abuse", "duplicate", "other"][reportReason.currentIndex]
        }

        background: Rectangle {
            radius: Theme.framedRadius(Theme.px(8))
            color: Theme.surfaceRaised
            border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
            border.color: Theme.borderStrong
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(10)

            SectionHeading {
                Layout.fillWidth: true
                title: "Report artwork"
                subtitle: "Reports are private and highlighted for the administrator."
            }

            Text {
                Layout.fillWidth: true
                text: "Report " + String(communityService.selectedArtwork.title || "this artwork")
                      + " by @" + String(communityService.selectedArtwork.creatorName || "Unknown") + "."
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(10.5)
                wrapMode: Text.Wrap
            }

            Label { text: "Reason" }
            KfpsComboBox {
                id: reportReason
                Layout.fillWidth: true
                model: ["Copyright or ownership", "Misleading listing", "Harassment or abuse", "Duplicate upload", "Other"]
                toolTipText: "Choose the closest reason so moderators can review it efficiently."
            }

            Label { text: "Details" }
            KfpsTextArea {
                id: reportDetails
                Layout.fillWidth: true
                Layout.fillHeight: true
                placeholderText: "Add useful context for the moderator"
                toolTipText: "Explain the issue without including private information."
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(8)
                GhostButton {
                    text: "Cancel"
                    toolTipText: "Close without sending a report."
                    onClicked: reportDialog.close()
                }
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    iconName: "reports"
                    text: "Submit Report"
                    enabled: !communityService.busy
                    toolTipText: "Submit one private report and highlight this listing for administrator review."
                    onClicked: {
                        communityService.reportSelected(reportDialog.reasonCode(), reportDetails.text)
                        reportDialog.close()
                        reportDetails.text = ""
                    }
                }
            }
        }
    }

    Popup {
        id: removeDialog
        modal: true
        focus: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        width: Math.min(root.width - Theme.px(48), Theme.px(520))
        height: Theme.px(270)
        x: Math.round((root.width - width) / 2)
        y: Math.round((root.height - height) / 2)
        padding: Theme.px(18)

        background: Rectangle {
            radius: Theme.framedRadius(Theme.px(8))
            color: Theme.surfaceRaised
            border.width: Theme.customFrameExclusive ? 0 : Math.max(1, Theme.px(1))
            border.color: Theme.danger
        }

        contentItem: ColumnLayout {
            spacing: Theme.px(12)
            SectionHeading {
                Layout.fillWidth: true
                title: "Remove this upload?"
                subtitle: "It will disappear from active browsing and cannot be restored from KFPS."
            }
            Text {
                Layout.fillWidth: true
                text: "Your local source file and existing downloads are not deleted. Moderation records remain for abuse prevention and audit history."
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(10.7)
                wrapMode: Text.Wrap
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                GhostButton {
                    text: "Keep Upload"
                    toolTipText: "Close without removing this artwork."
                    onClicked: removeDialog.close()
                }
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    text: "Remove Upload"
                    toolTipText: "Remove this artwork from the active community catalog."
                    onClicked: {
                        communityService.removeSelectedUpload()
                        removeDialog.close()
                    }
                }
            }
        }
    }
}
