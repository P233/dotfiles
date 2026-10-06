# macOS animation preferences

Verified against macOS 27.0 (26A428).
Keep Reduce Motion off; disable individual effects where supported.
This inventory covers native window, Dock, scrolling, Finder, Quick Look, and
Mail preferences. It is not an exhaustive
catalog of private macOS keys or third-party application animations.

Evidence: targeted `defaults read` calls, current documentation, and upstream
source. Stored values are not visual verification of every animation on
macOS 27. A missing key means no explicit override was found, not that the
effect is enabled or disabled.

## Recorded local state

[`defaults.sh`](defaults.sh) reproduces these explicitly stored preferences:

| Domain | Key | Local value | Effect |
| --- | --- | --- | --- |
| Global (`-g`) | `NSAutomaticWindowAnimationsEnabled` | `false` | Disable automatic window presentation animations in apps that honor it |
| `com.apple.dock` | `autohide` | `true` | Automatically hide the Dock |
| `com.apple.dock` | `autohide-delay` | `0` | Remove the reveal delay; this is a delay, not an animation |
| `com.apple.dock` | `autohide-time-modifier` | `0` | Remove Dock hide/show animation |
| `com.apple.dock` | `launchanim` | `false` | Disable launch-time icon bouncing |
| `com.apple.dock` | `mineffect` | `scale` | Use the scale minimize effect; animation remains |

The script does not write `com.apple.universalaccess reduceMotion`.

## Independent controls

These commands are references, not an additional install script. Only the
already configured values above are included in `defaults.sh`. Global AppKit
preferences apply only to consumers that honor them; custom application
animations can behave differently.

| Effect | Individual command | Evidence and limits | Local override |
| --- | --- | --- | --- |
| Automatic window presentation | `defaults write -g NSAutomaticWindowAnimationsEnabled -bool false` | Maintained [nix-darwin option][global-options]; does not establish animation-free minimization or full-screen transitions | `false`, recorded |
| Dock hide/show | `defaults write com.apple.dock autohide-time-modifier -float 0` | [Command reference][dock-time] tested through Sequoia; requires Dock auto-hide | `0`, recorded |
| Dock launch bounce | `defaults write com.apple.dock launchanim -bool false` | [Apple Dock settings][dock-settings]; distinct from attention-request bouncing | `false`, recorded |
| Dock hover magnification | `defaults write com.apple.dock magnification -bool false` | [Apple Dock settings][dock-settings]; disables hover enlargement | No explicit override |
| Dock attention bounce | `defaults write com.apple.dock no-bouncing -bool true` | [Community configuration][dock-bounce]; key is present in the local Dock binary, but behavior was not tested | No explicit override |
| Animated scrolling | `defaults write -g NSScrollAnimationEnabled -bool false` | Current [WebKit source][webkit-scroll] reads the preference; not a guarantee for every app or scrolling gesture | No explicit override |
| Scroll-edge rubber-band effect | `defaults write -g NSScrollViewRubberbanding -bool false` | Current [Chromium source][chromium-scroll] reads the preference; consumer-specific | No explicit override |
| Focus-ring animation | `defaults write -g NSUseAnimatedFocusRing -bool false` | Maintained [nix-darwin option][global-options]; macOS 27 behavior not tested | No explicit override |
| AppKit animated frame resizing | `defaults write -g NSWindowResizeTime -float 0` | [Apple documents the duration preference][resize-time]; zero requests zero duration in the default implementation. Apps can override it. This is not Dock minimization | No explicit override |

For Dock preferences, restart Dock after deliberately applying a change.
For application preferences, quit and reopen the affected application before
checking the exact interaction. `make install-macos` applies only the recorded
script and restarts Dock; it does not relaunch other apps.

## Historical or unverified candidates

These have no explicit local override and are not added to the installer.
Their appearance in old scripts is not evidence that they disable the effect
on macOS 27. In particular, writing an arbitrary key successfully proves only
that it was stored.

| Intended effect | Historical preference | Evidence / status |
| --- | --- | --- |
| Finder window / Get Info animations | `com.apple.finder DisableAllAnimations = true` | [Historical dotfiles][legacy-dotfiles]; key also exists in the local Finder binary. Runtime behavior untested |
| Finder window zoom | `com.apple.finder AnimateWindowZoom = false` | [Historical configuration][finder-zoom]; key exists in the local Finder binary. Runtime behavior untested |
| Quick Look presentation | `com.apple.finder QLPanelAnimationDuration = 0` or global `QLPanelAnimationDuration = 0` | Old recipes differ on the domain; [historical global example][legacy-animation-list]. No current verified recipe |
| Mail reply and send transitions | `com.apple.mail DisableReplyAnimations = true` / `DisableSendAnimations = true` | [Historical dotfiles][legacy-dotfiles]; no current version verification |
| Document version-browser transition | Global `NSDocumentRevisionsWindowTransformAnimation = false` | [Historical animation list][legacy-animation-list]; no current version verification |
| Column-browser movement | Global `NSBrowserColumnAnimationSpeedMultiplier = 0` | [Historical animation list][legacy-animation-list]; no current version verification |
| Full-screen toolbar transition | Global `NSToolbarFullScreenAnimationDuration = 0` | [Historical animation list][legacy-animation-list]; does not establish control over the entire full-screen transition |
| Mission Control / old Launchpad transitions | Dock `expose-animation-duration`, `springboard-show-duration`, `springboard-hide-duration`, `springboard-page-duration` | [Historical animation list][legacy-animation-list]; not verified for the current system interfaces |

## Remaining limitations

- **Minimize / restore:** Apple exposes `genie` and `scale` in its [Dock payload][dock-payload], not `none`. The hidden `suck` effect is also animated. No reliable native `defaults` command for zero-animation minimization on macOS 27 was established by this review.
- **Spaces, Mission Control, and native full screen:** no verified independent native no-animation setting was established. The old Dock `workspaces-swoosh-animation-off` key is not configured locally and is not treated as a working solution.
- **Spaces via a separate utility:** [noswoosh][noswoosh] advertises macOS 26.6+/27 support for three-finger swipes and Ctrl-arrow switching without global Reduce Motion. That is a third-party trigger-specific solution, not a `defaults` setting or a fix for every app-activation transition. It was not installed or tested here.
- Disabling a feature entirely (such as notifications, wallpaper clicks, or automatic Space switching) is not counted as disabling only its animation.

[dock-settings]: https://support.apple.com/guide/mac-help/change-desktop-dock-settings-mchlp1119/mac
[dock-payload]: https://developer.apple.com/documentation/devicemanagement/dock
[dock-time]: https://github.com/yannbertrand/macos-defaults/blob/main/docs/dock/autohide-time-modifier.md
[dock-bounce]: https://github.com/webpro/dotfiles/blob/main/macos/defaults.sh
[global-options]: https://github.com/nix-darwin/nix-darwin/blob/master/modules/system/defaults/NSGlobalDomain.nix
[webkit-scroll]: https://github.com/WebKit/WebKit/blob/main/Source/WebKit/Shared/Cocoa/WebPreferencesDefaultValuesCocoa.mm
[chromium-scroll]: https://github.com/chromium/chromium/blob/main/content/browser/theme_helper_mac.mm
[resize-time]: https://developer.apple.com/documentation/appkit/nswindow/animationresizetime(_:)
[legacy-dotfiles]: https://github.com/mathiasbynens/dotfiles/blob/main/.macos
[finder-zoom]: https://gist.github.com/sunaoka/6362077
[legacy-animation-list]: https://gist.github.com/fedek6/6f26dc662f5ed17143f0b30f67a3b8b2
[noswoosh]: https://github.com/mmathys/noswoosh
