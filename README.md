# MotionX-Editor
🎬 Your Personal Video Editing Bot!⚡ Create Pro-Level Edits Easily.🚀 Powered By @AniTimesNetwork


# वीडियो एडिटर टेलीग्राम बॉट (चरण 1)

फ़ीचर: ट्रिम, स्पीड, टेक्स्ट, म्यूज़िक, म्यूट, ऑडियो निकालना, कम्प्रेस। 2GB तक की वीडियो चलेगी।

## ज़रूरी वैल्यू (Environment Variables)
| नाम | कहाँ से मिलेगा |
|---|---|
| `BOT_TOKEN` | @BotFather |
| `API_ID` | https://my.telegram.org → API development tools |
| `API_HASH` | वहीं से |
| `MONGO_URI` | MongoDB Atlas → Connect → Drivers (फ्री क्लस्टर चलेगा) |
| `ADMIN_ID` | आपकी टेलीग्राम ID (डिफ़ॉल्ट: 6658706300) |

## Railway पर डिप्लॉय
1. यह फ़ोल्डर अपने GitHub रिपॉज़िटरी में अपलोड करें।
2. Railway → New Project → Deploy from GitHub repo।
3. Variables टैब में ऊपर की तीनों वैल्यू डालें।
4. Railway अपने आप Dockerfile से बना कर चला देगा।

## VPS पर
```
git clone <आपका-रिपो-लिंक> && cd <फ़ोल्डर>
docker build -t editorbot .
docker run -d --restart always -e BOT_TOKEN=... -e API_ID=... -e API_HASH=... editorbot
```

## कैसे चलता है
वीडियो भेजें → बटन चुनें → ज़रूरत हो तो इनपुट दें → एडिटेड वीडियो मिलेगा। हर एडिट पिछले एडिट के ऊपर जुड़ता जाता है। `/done` से फ़ाइलें हट जाती हैं।

## एडमिन कमांड (सिर्फ़ ADMIN_ID के लिए)
- `/stats` : यूज़र और एडिट की गिनती
- `/broadcast मैसेज` : सबको मैसेज (या किसी मैसेज पर रिप्लाई करके)
- `/ban ID` और `/unban ID`
