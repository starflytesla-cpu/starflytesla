"""ElevenLabs 預設音色（經 kie.ai 使用）。清單取自 kie.ai 文件 elevenlabs/text-to-speech-multilingual-v2。

試聽檔由 kie.ai 免費提供（不扣點數）：https://static.aiquickdraw.com/elevenlabs/voice/<voice_id>.mp3
recommended：適合產品 / 工廠短影音旁白的音色，前端預設只顯示這些。
"""

from dataclasses import dataclass

PREVIEW_URL = "https://static.aiquickdraw.com/elevenlabs/voice/{voice_id}.mp3"


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    description: str
    recommended: bool = False

    def out(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "recommended": self.recommended,
            "preview_url": PREVIEW_URL.format(voice_id=self.id),
        }


VOICES: list[Voice] = [
    Voice("EkK5I93UQWFDigLMpZcX", "James", "Husky, Engaging and Bold"),
    Voice("Z3R5wn05IrDiVCyEkUrK", "Arabella", "Mysterious and Emotive"),
    Voice("NNl6r8mD7vthiJatiJt1", "Bradford", "Expressive and Articulate"),
    Voice("YOq2y2Up4RgXP2HyXjE5", "Xavier", "Dominating, Metallic Announcer"),
    Voice("B8gJV1IhpuegLxdpXFOE", "Kuon", "Cheerful, Clear and Steady"),
    Voice("2zRM7PkgwBPiau2jvVXc", "Monika Sogam", "Deep and Natural"),
    Voice("1SM7GgM6IMuvQlz2BwM3", "Mark", "Casual, Relaxed and Light", recommended=True),
    Voice("5l5f8iK3YPeGga21rQIX", "Adeline", "Feminine and Conversational"),
    Voice("scOwDtmlUjD3prqpp97I", "Sam", "Support Agent"),
    Voice("NOpBlnGInO9m6vDvFkFC", "Spuds Oxley", "Wise and Approachable"),
    Voice("BZgkqPqms7Kj9ulSkVzn", "Eve", "Authentic, Energetic and Happy", recommended=True),
    Voice("wo6udizrrtpIxWGp2qJk", "Northern Terry", ""),
    Voice("gU0LNdkMOQCOrPrwtbee", "British Football Announcer", ""),
    Voice("DGzg6RaUqxGRTHSBjfgF", "Brock", "Commanding and Loud Sergeant"),
    Voice("x70vRnQBMBu4FAYhjJbO", "Nathan", "Virtual Radio Host", recommended=True),
    Voice("Sm1seazb4gs7RSlUVw7c", "Anika", "Animated, Friendly and Engaging"),
    Voice("P1bg08DkjqiVEzOn76yG", "Viraj", "Rich and Soft"),
    Voice("qDuRKMlYmrm8trt5QyBn", "Taksh", "Calm, Serious and Smooth"),
    Voice("qXpMhyvQqiRxWQs4qSSB", "Horatius", "Energetic Character Voice"),
    Voice("TX3LPaxmHKxFdv7VOQHJ", "Liam", "Energetic, Social Media Creator", recommended=True),
    Voice("N2lVS1w4EtoT3dr4eOWO", "Callum", "Husky Trickster"),
    Voice("FGY2WhTYpPnrIDTdsKH5", "Laura", "Enthusiast, Quirky Attitude"),
    Voice("kPzsL2i3teMYv0FxEYQ6", "Brittney", "Social Media Voice - Fun, Youthful & Informative", recommended=True),
    Voice("UgBBYS2sOqTuMpoF3BR0", "Mark", "Natural Conversations", recommended=True),
    Voice("hpp4J3VqNfWAUOO0d1Us", "Bella", "Professional, Bright, Warm", recommended=True),
    Voice("nPczCjzI2devNBz1zQrb", "Brian", "Deep, Resonant and Comforting", recommended=True),
    Voice("uYXf8XasLslADfZ2MB4u", "Hope", "Bubbly, Gossipy and Girly"),
    Voice("gs0tAILXbY5DNrJrsM6F", "Jeff", "Classy, Resonating and Strong"),
    Voice("DTKMou8ccj1ZaWGBiotd", "Jamahal", "Young, Vibrant, and Natural", recommended=True),
    Voice("vBKc2FfBKJfcZNyEt1n6", "Finn", "Youthful, Eager and Energetic"),
    Voice("DYkrAHD8iwork3YSUBbs", "Tom", "Conversations & Books"),
    Voice("56AoDkrOh6qfVPDXZ7Pt", "Cassidy", "Crisp, Direct and Clear", recommended=True),
    Voice("eR40ATw9ArzDf9h3v7t7", "Addison 2.0", "Australian Audiobook & Podcast"),
    Voice("g6xIsTj2HwM6VR4iXFCw", "Jessica Anne Bogart", "Chatty and Friendly", recommended=True),
    Voice("lcMyyd2HUfFzxdCaC4Ta", "Lucy", "Fresh & Casual", recommended=True),
    Voice("6aDn1KB0hjpdcocrUkmq", "Tiffany", "Natural and Welcoming", recommended=True),
    Voice("Sq93GQT4X1lKDXsQcixO", "Felix", "Warm, Positive & Contemporary RP", recommended=True),
    Voice("flHkNRp1BlvT73UL6gyz", "Jessica Anne Bogart", "Eloquent Villain"),
    Voice("9yzdeviXkFddZ4Oz8Mok", "Lutz", "Chuckling, Giggly and Cheerful"),
    Voice("pPdl9cQBQq4p6mRkZy2Z", "Emma", "Adorable and Upbeat"),
    Voice("zYcjlYFOd3taleS0gkk3", "Edward", "Loud, Confident and Cocky"),
    Voice("nzeAacJi50IvxcyDnMXa", "Marshal", "Friendly, Funny Professor"),
    Voice("ruirxsoakN0GWmGNIo04", "John Morgan", "Gritty, Rugged Cowboy"),
    Voice("TC0Zp7WVFzhA8zpTlRqV", "Aria", "Sultry Villain"),
    Voice("ljo9gAlSqKOvF6D8sOsX", "Viking Bjorn", "Epic Medieval Raider"),
    Voice("PPzYpIqttlTYA83688JI", "Pirate Marshal", ""),
    Voice("8JVbfL6oEdmuxKn5DK2C", "Johnny Kid", "Serious and Calm Narrator"),
    Voice("iCrDUkL56s3C8sCRl7wb", "Hope", "Poetic, Romantic and Captivating"),
    Voice("wJqPPQ618aTW29mptyoc", "Ana Rita", "Smooth, Expressive and Bright"),
    Voice("EiNlNiXeDU1pqqOPrYMO", "John Doe", "Deep"),
    Voice("4YYIPFl9wE5c4L2eu2Gb", "Burt Reynolds™", "Deep, Smooth and Clear"),
    Voice("6F5Zhi321D3Oq7v1oNT4", "Hank", "Deep and Engaging Narrator", recommended=True),
    Voice("YXpFCvM1S3JbWEJhoskW", "Wyatt", "Wise Rustic Cowboy"),
    Voice("LG95yZDEHg6fCZdQjLqj", "Phil", "Explosive, Passionate Announcer"),
    Voice("CeNX9CMwmxDxUF5Q2Inm", "Johnny Dynamite", "Vintage Radio DJ"),
    Voice("aD6riP1btT197c6dACmy", "Rachel M", "Pro British Radio Presenter"),
    Voice("mtrellq69YZsNwzUSyXh", "Rex Thunder", "Deep N Tough"),
    Voice("dHd5gvgSOzSfduK4CvEg", "Ed", "Late Night Announcer"),
    Voice("eVItLK1UvXctxuaRV2Oq", "Jean", "Alluring and Playful Femme Fatale"),
    Voice("esy0r39YPLQjOczyOib8", "Britney", "Calm and Calculative Villain"),
    Voice("Tsns2HvNFKfGiNjllgqo", "Sven", "Emotional and Nice"),
    Voice("1U02n4nD6AdIZ9CjF053", "Viraj", "Smooth and Gentle"),
    Voice("AeRdCCKzvd23BpJoofzx", "Nathaniel", "Engaging, British and Calm", recommended=True),
    Voice("LruHrtVF6PSyGItzMNHS", "Benjamin", "Deep, Warm, Calming"),
    Voice("1wGbFxmAM3Fgw63G1zZJ", "Allison", "Calm, Soothing and Meditative"),
    Voice("hqfrgApggtO1785R4Fsn", "Theodore HQ", "Serene and Grounded"),
    Voice("MJ0RnG71ty4LH3dvNfSd", "Leon", "Soothing and Grounded"),
]

VOICES_BY_ID = {v.id: v for v in VOICES}
