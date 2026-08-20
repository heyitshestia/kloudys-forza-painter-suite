import QtQuick 6.7

Item {
    id: root
    objectName: "CachedPageHost"

    property string currentPage: "create"
    readonly property var currentLoader: ({
        create: createLoader,
        outputs: outputsLoader,
        liveries: liveriesLoader,
        community: communityLoader,
        editor: editorLoader,
        tools: toolsLoader,
        support: supportLoader,
        help: helpLoader,
        update: updateLoader,
        settings: settingsLoader,
        generate: generateLoader,
        images: imagesLoader,
        reports: reportsLoader,
        credits: creditsLoader
    })[currentPage] || createLoader
    readonly property var item: currentLoader ? currentLoader.item : null

    signal pageLoaded(string page, var pageItem)

    function retainAfterFirstLoad(loader, selected) {
        return selected || loader.item !== null
    }

    Loader {
        id: createLoader
        anchors.fill: parent
        visible: root.currentPage === "create"
        active: root.retainAfterFirstLoad(createLoader, visible)
        asynchronous: false
        source: "../pages/CreatePage.qml"
        onLoaded: root.pageLoaded("create", item)
    }

    Loader {
        id: outputsLoader
        anchors.fill: parent
        visible: root.currentPage === "outputs"
        active: root.retainAfterFirstLoad(outputsLoader, visible)
        asynchronous: true
        source: "../pages/JsonPage.qml"
        onLoaded: root.pageLoaded("outputs", item)
    }

    Loader {
        id: liveriesLoader
        anchors.fill: parent
        visible: root.currentPage === "liveries"
        active: root.retainAfterFirstLoad(liveriesLoader, visible)
        asynchronous: true
        source: "../pages/LiveryPage.qml"
        onLoaded: root.pageLoaded("liveries", item)

        Binding {
            target: liveriesLoader.item
            property: "pageActive"
            value: liveriesLoader.visible
            when: liveriesLoader.item !== null
        }
    }

    Loader {
        id: communityLoader
        anchors.fill: parent
        visible: root.currentPage === "community"
        active: root.retainAfterFirstLoad(communityLoader, visible)
        asynchronous: true
        source: "../pages/CommunityPage.qml"
        onLoaded: root.pageLoaded("community", item)
    }

    Loader {
        id: editorLoader
        anchors.fill: parent
        visible: root.currentPage === "editor"
        active: root.retainAfterFirstLoad(editorLoader, visible)
        asynchronous: true
        source: "../pages/EditorPage.qml"
        onLoaded: root.pageLoaded("editor", item)
    }

    Loader {
        id: toolsLoader
        anchors.fill: parent
        visible: root.currentPage === "tools"
        active: root.retainAfterFirstLoad(toolsLoader, visible)
        asynchronous: true
        source: "../pages/ToolsPage.qml"
        onLoaded: root.pageLoaded("tools", item)
    }

    Loader {
        id: supportLoader
        anchors.fill: parent
        visible: root.currentPage === "support"
        active: root.retainAfterFirstLoad(supportLoader, visible)
        asynchronous: true
        source: "../pages/SupportPage.qml"
        onLoaded: root.pageLoaded("support", item)
    }

    Loader {
        id: helpLoader
        anchors.fill: parent
        visible: root.currentPage === "help"
        active: root.retainAfterFirstLoad(helpLoader, visible)
        asynchronous: true
        source: "../pages/HelpPage.qml"
        onLoaded: root.pageLoaded("help", item)
    }

    Loader {
        id: updateLoader
        anchors.fill: parent
        visible: root.currentPage === "update"
        active: root.retainAfterFirstLoad(updateLoader, visible)
        asynchronous: true
        source: "../pages/UpdatePage.qml"
        onLoaded: root.pageLoaded("update", item)
    }

    Loader {
        id: settingsLoader
        anchors.fill: parent
        visible: root.currentPage === "settings"
        active: root.retainAfterFirstLoad(settingsLoader, visible)
        asynchronous: true
        source: "../pages/SettingsPage.qml"
        onLoaded: root.pageLoaded("settings", item)
    }

    Loader {
        id: generateLoader
        anchors.fill: parent
        visible: root.currentPage === "generate"
        active: root.retainAfterFirstLoad(generateLoader, visible)
        asynchronous: true
        source: "../pages/GeneratePage.qml"
        onLoaded: root.pageLoaded("generate", item)
    }

    Loader {
        id: imagesLoader
        anchors.fill: parent
        visible: root.currentPage === "images"
        active: root.retainAfterFirstLoad(imagesLoader, visible)
        asynchronous: true
        source: "../pages/ImagesPage.qml"
        onLoaded: root.pageLoaded("images", item)
    }

    Loader {
        id: reportsLoader
        anchors.fill: parent
        visible: root.currentPage === "reports"
        active: root.retainAfterFirstLoad(reportsLoader, visible)
        asynchronous: true
        source: "../pages/ReportsPage.qml"
        onLoaded: root.pageLoaded("reports", item)
    }

    Loader {
        id: creditsLoader
        anchors.fill: parent
        visible: root.currentPage === "credits"
        active: root.retainAfterFirstLoad(creditsLoader, visible)
        asynchronous: true
        source: "../pages/CreditsPage.qml"
        onLoaded: root.pageLoaded("credits", item)
    }
}
