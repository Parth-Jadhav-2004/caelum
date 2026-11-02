# Caelum 0.3.4

Caelum 0.3.4 updates Home, Settings, navigation, and background operation.

- Restore the sentence-style Settings page, with System, Light, and Dark theme selection inside Settings and automatic saving.
- Add a collapsible sidebar with the supplied collapse icon and a Statistics page between Home and History. Remove green button outlines while retaining keyboard focus indicators.
- Show five recent dictations beside a monthly daily-usage calendar. Calendar tooltips show the number of words dictated.
- Replace today's word count on Home with cumulative words dictated. Remove the session count and Ready pill, and simplify Statistics by removing weekly word and output-dispatch metrics.
- Start the dictation service when the app opens, reusing an existing service. Add a system tray menu for Open Caelum, Settings, Start/Pause/Resume dictation, and Quit Caelum. Closing the window keeps Caelum in a supported system tray; Quit stops the app and service.
- Preserve completed onboarding when managing keys or changing providers, so setup stays complete after restarting.

The cumulative word total starts from existing saved history and adds future saved dictations. Retention and deletion do not reduce it; dictations deleted before this feature cannot be recovered. With history saving off, new dictations do not add to the counter. No audio is saved by this feature.

Packages are available for Ubuntu 24.04, Ubuntu 26.04, Arch, and Fedora 43. Downloads contain four packages, update.json, and update.json.sig. Signing, package hash verification, and exact distribution/version matching remain unchanged. Settings, keys, and history are preserved when upgrading.

Tray placement is controlled by your desktop. The Caelum-only placement on the left of the local Omarchy bar is a user configuration, not a system layout change made by the package.
