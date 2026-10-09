use framework "AppKit"
use scripting additions

on run arguments
	set applicationInstance to current application's NSApplication's sharedApplication()
	applicationInstance's setActivationPolicy:(current application's NSApplicationActivationPolicyAccessory)
	set panelWidth to 280
	set panelHeight to 74
	set panelBounds to current application's NSMakeRect(0, 0, panelWidth, panelHeight)
	set panel to current application's NSPanel's alloc()'s initWithContentRect:panelBounds styleMask:(current application's NSWindowStyleMaskNonactivatingPanel) backing:(current application's NSBackingStoreBuffered) defer:false
	panel's setTitle:"Focus reminder"
	panel's setOpaque:false
	panel's setBackgroundColor:(current application's NSColor's clearColor())
	panel's setLevel:(current application's NSFloatingWindowLevel)
	panel's setHidesOnDeactivate:false
	panel's setIgnoresMouseEvents:true
	panel's setHasShadow:true
	panel's setReleasedWhenClosed:false
	panel's setCollectionBehavior:(((current application's NSWindowCollectionBehaviorCanJoinAllSpaces) as integer) + ((current application's NSWindowCollectionBehaviorFullScreenAuxiliary) as integer) + ((current application's NSWindowCollectionBehaviorTransient) as integer))

	set backdrop to current application's NSVisualEffectView's alloc()'s initWithFrame:panelBounds
	backdrop's setMaterial:(current application's NSVisualEffectMaterialHUDWindow)
	backdrop's setBlendingMode:(current application's NSVisualEffectBlendingModeBehindWindow)
	backdrop's setState:(current application's NSVisualEffectStateActive)
	-- Behind-window material needs its own mask; layer clipping leaves square corners.
	set roundedMask to current application's NSImage's alloc()'s initWithSize:(current application's NSMakeSize(panelWidth, panelHeight))
	roundedMask's lockFocus()
	current application's NSColor's blackColor()'s setFill()
	(current application's NSBezierPath's bezierPathWithRoundedRect:panelBounds xRadius:18 yRadius:18)'s fill()
	roundedMask's unlockFocus()
	backdrop's setMaskImage:roundedMask
	set label to current application's NSTextField's labelWithString:"1 minute remaining"
	label's setFont:(current application's NSFont's systemFontOfSize:22 weight:(current application's NSFontWeightMedium))
	label's setAlignment:(current application's NSTextAlignmentCenter)
	label's setFrame:(current application's NSMakeRect(20, 18, panelWidth - 40, 32))
	backdrop's addSubview:label
	panel's setContentView:backdrop

	set {{screenX, screenY}, {screenWidth, screenHeight}} to current application's NSScreen's mainScreen()'s frame()
	panel's setFrameOrigin:(current application's NSMakePoint(screenX + (screenWidth - panelWidth) / 2, screenY + (screenHeight - panelHeight) / 2))
	set earliest to (item 1 of arguments) as real
	set latest to (item 2 of arguments) as real
	set now to current application's NSDate's |date|()'s timeIntervalSince1970()
	if now < earliest or now > latest then return
	panel's orderFrontRegardless()
	current application's NSRunLoop's currentRunLoop()'s runUntilDate:(current application's NSDate's dateWithTimeIntervalSinceNow:5)
	panel's orderOut:(missing value)
end run
