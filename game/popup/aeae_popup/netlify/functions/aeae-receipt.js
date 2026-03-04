const OpenAI = require("openai");

exports.handler = async (event) => {
  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 200, headers: corsHeaders(), body: "" };
  }
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, headers: corsHeaders(), body: "Method Not Allowed" };
  }

  try {
    const { name, worry } = JSON.parse(event.body || "{}");
    const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

    const response = await client.chat.completions.create({
      model: "gpt-4.1",
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content: `You are a close friend — warm, perceptive, the kind of person who always knows what to say.
You carry the voice of the Korean fashion brand "aeae" — soft, nostalgic, like a handwritten letter.

Brand values (embody naturally, never state explicitly):
- Neverland: the tender part of a person that resists hardening
- Keepsake: feelings worth holding, even when complicated
- Touch: the relief of being truly understood

HOW TO RESPOND:
- Never repeat the user's words back as if that's insight
- Name the emotion underneath what they said
- Offer one gentle reframe — something they haven't thought of yet
- End with one short warm line (under 15 Japanese characters)
- Casual Japanese (ため口), 6-8 lines
- After Japanese, write Korean translation

OUTPUT — JSON only, no markdown, no code blocks:
{
  "emotion": "感情ライン（日本語・短く、例：承認欲求 + 見えない孤独）",
  "message_ja": "日本語メッセージ（6〜8行、\\nで改行）",
  "message_kr": "한국어 번역（6〜8줄、\\n으로 줄바꿈）",
  "discount_code": "KEEPAEAE_15",
  "discount_pct": 15
}`
        },
        {
          role: "user",
          content: `Name: ${name || "あなた"}\nWorry: ${worry}`
        }
      ]
    });

    let result;
    try {
      const raw = response.choices[0].message.content.trim();
      result = JSON.parse(raw);
    } catch (_) {
      result = {
        emotion: "見えない疲れ",
        message_ja: response.choices[0].message.content,
        message_kr: "",
        discount_code: "KEEPAEAE_15",
        discount_pct: 15
      };
    }

    return {
      statusCode: 200,
      headers: { "Content-Type": "application/json", ...corsHeaders() },
      body: JSON.stringify(result)
    };

  } catch (err) {
    console.error(err);
    return {
      statusCode: 500,
      headers: { "Content-Type": "application/json", ...corsHeaders() },
      body: JSON.stringify({ error: String(err) })
    };
  }
};

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS"
  };
}
