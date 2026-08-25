import type { ComposerMode } from '@/types/api';

/**
 * Opening prompts for a blank thread.
 *
 * Written for the people who actually use this — small businesses making their own social media —
 * rather than the generic assistant examples that shipped first. In Hindi, because that is the
 * language most of them write their captions in.
 */
export const STARTERS: Record<ComposerMode, string[]> = {
  chat: [
    'नए प्रोडक्ट लॉन्च के लिए इंस्टाग्राम कैप्शन लिखो, हैशटैग के साथ',
    'मेरे कैफ़े के लिए एक हफ़्ते का सोशल मीडिया कंटेंट प्लान बनाओ',
    'फ़ेस्टिव सेल का WhatsApp ब्रॉडकास्ट मैसेज लिखो — छोटा और असरदार',
    'ग्राहक के रिव्यू पर 30 सेकंड की रील स्क्रिप्ट चाहिए',
  ],
  image: [
    'प्रोडक्ट फ़ोटो को साफ़ सफ़ेद बैकग्राउंड पर स्टूडियो जैसा बनाओ',
    'दिवाली ऑफ़र का पोस्टर — 50% छूट, चमकदार रंग',
    'इंस्टाग्राम स्टोरी साइज़ में मेन्यू का डिज़ाइन बनाओ',
    'दुकान के लिए सोशल मीडिया बैनर — नाम और फ़ोन नंबर के साथ',
  ],
};

export const HEADINGS: Record<ComposerMode, { title: string; subtitle: string }> = {
  chat: {
    title: 'आज क्या लिखवाना है?',
    subtitle: 'कैप्शन, पोस्ट, स्क्रिप्ट — कुछ भी पूछो। फ़ोटो लगाकर उसी के बारे में लिखवा भी सकते हो।',
  },
  image: {
    title: 'आज क्या बनवाना है?',
    subtitle: 'जो चाहिए वो लिखो, या अपनी फ़ोटो लगाकर उसे बदलवाओ।',
  },
};
