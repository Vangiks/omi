// The bar's send path. Both bar surfaces funnel through here — typed submits and
// PTT commits. The bar is its OWN renderer process, so a send hops the bar→main
// bridge to the main window's chat engine.
export function sendFromBar(text: string, fromVoice: boolean): void {
  if (!text.trim()) return
  // Onboarding: the user asked something in the bar.
  window.omiOverlay.notifyAsked()
  window.omiBar.sendChat(text, fromVoice)
}
