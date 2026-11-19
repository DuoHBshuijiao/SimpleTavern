import { applyContentRegexDisplay } from './contentRegex'
import type { ChatContentRegexRule } from '../types/models'

self.onmessage = (event: MessageEvent<{ text: string; rules: ChatContentRegexRule[] }>) => {
  self.postMessage(applyContentRegexDisplay(event.data.text, event.data.rules))
}
