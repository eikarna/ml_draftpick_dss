from paddleocr import PaddleOCR
from thefuzz import fuzz

def DEFAULT_SIMILARITY(*args, **kwargs):
    return 0.01 * fuzz.token_sort_ratio(*args, **kwargs)

# use en if text contains numbers
# otherwise use latin

class OCR:
    def __init__(self, has_number=True, similarity=DEFAULT_SIMILARITY):
        lang = "en" if has_number else "latin"
        self.ocr = PaddleOCR(use_angle_cls=True, lang=lang)
        self.similarity = similarity

    def read(self, img):
        text = self.ocr.ocr(
            img, det=False, cls=False
        )[0][0]
        if not text:
            return None
        return text[0].strip().lower()

    def read_history_player_name(self, img, throw=True):
        try:
            name_text = self.read(img)
            name_text = name_text.replace("`", "'").replace('"', "'").rsplit("'", maxsplit=1)
            if (not len(name_text) == 2):
                raise Exception("BAD_SS_HISTORY")
            if self.similarity(name_text[-1].rsplit(" ", 2)[-1], "history") < 0.8:
                raise Exception("BAD_SS_HISTORY")
            name_text = name_text[0]
            return name_text
        except Exception as ex:
            if throw:
                raise
            return None
    
    def read_num(self, img):
        num = self.read(img)
        num = num.strip(".").replace("!", "").replace("/", "").replace("%", "")
        return num
    
    def read_int(self, img):
        num = self.read_num(img)
        return int(num.replace(".", ""))
    
    def read_team_kills(self, img, throw=True):
        try:
            return self.read_int(img)
        except ValueError as ex:
            if throw:
                raise Exception(f"BAD_SS_KILL: {ex}")
            return None

    def read_score(self, img, throw=True):
        score_text = self.read_num(img)
        try:
            replace = float(score_text) >= 100
            replace = -2 if replace else -1
            score_text = score_text if "." in score_text else (score_text[:replace] + "." + score_text[-1:])
            score_f = float(score_text)
            score_f = score_f if score_f < 70 else (score_f - 60)
            return score_f
        except ValueError as ex:
            if throw:
                raise Exception(f"BAD_SS_SCORE: {ex}")
            return None
    
    def read_battle_id(self, img, throw=True):
        text = self.read(img)
        try:
            return int(text.split(" ")[-1].strip())
        except ValueError as ex:
            if throw:
                raise Exception(f"BAD_SS_BATTLE_ID: {ex}")
            return None
    
    def read_match_duration(self, img):
        text = self.read(img)
        time = text.split(" ")[-1].strip()[:5].replace(".", ":")
        return time
    
    def read_match_duration_mins(self, img, throw=True):
        time = self.read_match_duration(img)
        try:
            mins, sec = [int(x) for x in time.split(":")]
            total_mins = mins + sec/60
            return total_mins
        except ValueError as ex:
            if throw:
                raise Exception(f"BAD_SS_DURATION: {ex}")
            return None
