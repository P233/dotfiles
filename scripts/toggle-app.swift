import AppKit

guard CommandLine.arguments.count > 1 else { exit(1) }
let appName = CommandLine.arguments[1]
let workspace = NSWorkspace.shared
let frontmost = workspace.frontmostApplication

/// Check if the app has any visible windows on screen (layer 0 = normal windows).
func appHasWindows(_ app: NSRunningApplication) -> Bool {
    let windowList = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
    return windowList?.contains(where: {
        ($0[kCGWindowOwnerPID as String] as? Int) == Int(app.processIdentifier) &&
        ($0[kCGWindowLayer as String] as? Int) == 0
    }) ?? false
}

/// Send an "open application" Apple Event to create a new window (or launch the app).
func openNewWindow(_ appName: String) {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    process.arguments = ["-a", appName]
    try? process.run()
}

// Toggle logic:
// 1. App is frontmost + has windows   → hide
// 2. App is frontmost + no windows    → open a new window (instead of hiding into nothing)
// 3. App is running but not frontmost → activate, and open a new window if none exists
// 4. App is not running               → launch
if frontmost?.localizedName == appName {
    if appHasWindows(frontmost!) {
        frontmost?.hide()
    } else {
        openNewWindow(appName)
    }
} else if let app = workspace.runningApplications.first(where: { $0.localizedName == appName }) {
    app.activate()
    if !appHasWindows(app) {
        openNewWindow(appName)
    }
} else {
    openNewWindow(appName)
}
