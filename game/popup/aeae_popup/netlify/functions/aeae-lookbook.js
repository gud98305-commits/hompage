const OpenAI = require("openai");

exports.handler = async (event) => {
  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 200, headers: corsHeaders(), body: "" };
  }
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, headers: corsHeaders(), body: "Method Not Allowed" };
  }

  try {
    const { lookId, topName, bottomName, accName } = JSON.parse(event.body || "{}");
    const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

    // ── STEP 1: Style description ──
    const styleRes = await client.chat.completions.create({
      model: "gpt-4.1",
      messages: [
        {
          role: "system",
          content: `You are the warm, nostalgic voice of aeae, a Korean fashion brand.
Speak like a close friend writing a handwritten note — soft, intimate, slightly dreamy.
Write in casual Japanese (ため口). 2–3 short lines only.
Describe the vibe and mood of this outfit — what kind of day it's made for, what feeling it gives off.
Then write Korean translation of the same content.
Separate Japanese and Korean with exactly: \n\n---\n\n
Output plain text only. No JSON, no labels.`
        },
        {
          role: "user",
          content: `Look #${String(lookId).padStart(2, '0')}
Top: ${topName}
Bottom: ${bottomName}
Acc: ${accName || 'アクセなし'}`
        }
      ]
    });

    const styleFull = styleRes.choices[0].message.content.trim();
    const [styleJa, styleKr] = styleFull.split('---').map(s => s.trim());

    // ── STEP 2: Fortune based on style ──
    const fortuneRes = await client.chat.completions.create({
      model: "gpt-4.1",
      messages: [
        {
          role: "system",
          content: `You are the warm, nostalgic voice of aeae, a Korean fashion brand.
Speak like a close friend who can read the energy of what someone is wearing.
Write in casual Japanese (ため口). 2–3 short lines only.
Based on the outfit's style vibe, tell today's fashion fortune — positive, dreamy, a little magical.
Make it feel like the outfit is speaking directly to the person wearing it.
Then write Korean translation of the same content.
Separate Japanese and Korean with exactly: \n\n---\n\n
Output plain text only. No JSON, no labels.`
        },
        {
          role: "user",
          content: `このコーデのスタイル説明:\n${styleJa}\n\nこのコーデを着る人の今日の運勢を教えて。`
        }
      ]
    });

    const fortuneFull = fortuneRes.choices[0].message.content.trim();
    const [fortuneJa, fortuneKr] = fortuneFull.split('---').map(s => s.trim());

    return {
      statusCode: 200,
      headers: { "Content-Type": "application/json", ...corsHeaders() },
      body: JSON.stringify({
        style: styleJa,
        styleKr: styleKr || '',
        fortune: fortuneJa,
        fortuneKr: fortuneKr || ''
      })
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
