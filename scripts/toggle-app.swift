import AppKit

guard CommandLine.arguments.count > 1 else { exit(1) }
let appName = CommandLine.arguments[1]
let workspace = NSWorkspace.shared
let frontmost = workspace.frontmostApplication

if frontmost?.localizedName == appName {
    frontmost?.hide()
} else if let app = workspace.runningApplications.first(where: { $0.localizedName == appName }) {
    app.activate()
} else {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    process.arguments = ["-a", appName]
    try? process.run()
}
