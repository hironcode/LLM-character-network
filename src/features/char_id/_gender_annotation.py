
# import libraries
from collections import defaultdict
import spacy
from spacy.matcher import Matcher

# import local files
from src.data import make_dataset

class GenderAnnotation:
    def __init__(self, nlp, doc, chars:defaultdict):
        """
        :param chars: the defalut dictionary generated in CharacterIdentification. Vulnerable to format change.
        """

        self.nlp = nlp
        self.doc = doc
        self.chars = chars

    def _annotate_gender_by_titiles(self):
        # identification by titles
        female_titles = ["mrs.", "mrs", "miss.", "miss", "mis.", "mis"]
        male_titles = ["mr.", "mr"]
        name_genders = {}
        for name in list(self.chars.keys()):
            name_genders[name] = []

        title_name = self._match_gender_title()
        for title, name in title_name:
            # if the name is not in the default dict, skip the process
            if name.text not in self.chars.keys():
                continue

            if title.text.lower() in female_titles:
                name_genders[name.text].append("FEMALE")
            elif title.text.lower() in male_titles:
                name_genders[name.text].append("MALE")

        # re-assign the most frequent gender to each person
        for name, gender in name_genders.items():
            size = len(gender)

            if size == 0:
                name_genders[name] = "UNKNOWN"
            elif gender.count("FEMALE") >= size/2:
                name_genders[name] = "FEMALE"
            elif gender.count("MALE") >= size/2:
                name_genders[name] = "MALE"
        print(f"_annotate_gender_by_titles: "
              f"{name_genders}")
        return name_genders

    def _match_gender_title(self):
        # (1) honorific matcher

        # use REGEX experession
        #   [ri] means a token has either r or s after M
        #   s{0,2} means the s can appear 0 through 2 times
        #   .? means the period can appear 0 or 1 time
        # with the REGEX expression, we can cover Mr., Mrs., Miss., and Mis., with/without a following period
        pattern = [
            {"TEXT": {"REGEX": "M[ri]s{0,2}\.?"}},
            {"POS": "PROPN", "OP": "+"}
        ]

        matcher = Matcher(self.nlp.vocab)
        matcher.add("TITLE", [pattern])
        matches = matcher(self.doc)
        title_name = list()
        for match in matches:
            title_name.append((self.doc[match[1]], self.doc[match[1]+1:match[2]]))
        return title_name

    def _annotate_gender_by_names(self):
        # identificaiton by name
        male_names, female_names = make_dataset.get_namelists()
        names = list(self.chars.keys())
        name_genders = {}

        for name in names:
            if name in male_names:
                name_genders[name] = "MALE"
            elif name in female_names:
                name_genders[name] = "FEMALE"
            else:
                name_genders[name] = "UNKNOWN"

        print(f"_annotate_gender_by_names:"
              f"{name_genders}")
        return name_genders

    def _annotate_gender_by_pronouns(self):
        names = list(self.chars.keys())
        name_genders = {}
        # identification by pronouns
        for name in names:
            # get a list of indexes of a propernoun appearing in the doc
            spans = self.chars[name][1]
            # get a list of pronouns appearing in the sentences that each propernoun is in
            pronouns = self._find_pronouns(spans)
            # assign the most likely gender to the character from the list of pronouns
            gender = self._assign_gender_by_pronouns(pronouns)
            name_genders[name] = gender

        print(f"_annotate_gender_by_names:"
              f"{name_genders}")
        return name_genders

    def _find_pronouns(self, token_idxes):
        mentions = []
        i = 0
        j = 0
        start = 0
        end = 0
        while j < len(list(self.doc.sents))-1:

            # print(f"j: {j}")
            # print(f"i: {i}")

            # i is for indexing a token
            # j is for indexing a sentence
            # start is the number of tokens until the beginning of each sentence
            # end is the number of tlekns until the end of each sentence
            token_idx = token_idxes[i]

            # print(token_idx)

            # if the sentence is not the first one, add the length of previous sentence to start
            if j > 0:
                start += len(list(list(self.doc.sents)[j-1]))
            sent = list(self.doc.sents)[j]
            end += len(list(sent))

            # print(sent)
            # print(f"start: {start}")
            # print(f"end: {end}")

            # continue to scan through teh sentence if the token index is inside sentence
            # purposefully, also extract the pronouns even if a new token index appears in the sentence,
            # assuming that concurrent appearences strongly indicate the gender tallying the pronouns
            while start <= token_idx < end and i < len(token_idxes)-1:
                pronouns = self._match_pronouns(sent)
                mentions += pronouns
                i += 1
                token_idx = token_idxes[i]

                # print(pronouns)
                # print("\t =====================================================================")

            j += 1

            # print("------------------------------------------------")

        return mentions

    def _match_pronouns(self, sent):
        """
        find pronouns from a sentence
        :param sent: Spacy Sentence
        :return: a list of pronouns in SpaCy token
        """
        male_pattern = [
            {"LOWER": {"IN": ["he", "his", "him", "himself"]}}
        ]
        female_pattern = [
            {"LOWER": {"IN": ["she", "her", "hers", "herself"]}}
        ]

        matcher = Matcher(self.nlp.vocab)
        matcher.add("PRONOUN", [male_pattern, female_pattern])
        matches = matcher(sent)

        pronouns = []
        for match in matches:
            # print(f"match: {match}")
            pronouns.append(sent[match[1]:match[2]])
        return pronouns

    def _assign_gender_by_pronouns(self, pronouns):
        """
        This method takes a list of pronouns and determines the gender based on the most appearing gender categories
        :param pronouns: list
        :return: the most likely gender
        """
        male, female = 0, 0
        male_pronouns = ["he", "his", "him", "himself"]
        female_pronouns = ["she", "her", "hers", "herself"]
        for pron in pronouns:
            if pron.text.lower() in male_pronouns:
                male += 1
            elif pron.text.lower() in female_pronouns:
                female += 1

        gender = 'UNKNOWN'
        if male > female:
            gender= "MALE"
        elif female > male:
            gender= "FEMALE"
        elif female == male:
            gender= "UNKNOWN"
        return gender