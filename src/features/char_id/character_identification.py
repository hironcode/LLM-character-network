"""
This .py file is a set of functions that help identify characters in a text

Steps:
(1) use Named Entitiy Recognition (NER) to identify person entities
(2) automatically anotate a gender to each entity based on:
    (a) honorific or titles such as Mr., Mrs., or Lord etc...
    (b) lists of male first names and female first names
    (c) detecting pronouns such as him, her, his, her, himself, and herself etc...
(3) integrate person entities that refer to the same characters by:
    (a) grouping person names with similar names (refer to
    https://aclanthology.org/W14-0905/ for more information)
    (b) by excluding pairs that satisfy the following criteria:
        "(1) the inferred genders of both names differ
        (2) both names share a common surname but different first names
        (3) the honorific of both names differ, e.g., “Miss” and “Mrs.”"
        (reference: https://aclanthology.org/D15-1088/)
"""

# import libraries
import spacy
from spacy.matcher import Matcher
from collections import defaultdict
from unionfind import unionfind

# import local files
from src.data import make_dataset
from src.features.char_id._gender_annotation import GenderAnnotation
from src.features.char_id._unify_occurences import OccurenceUnification
from src.tools.character_entity import Character
from src.models import model_saver
from src.tools.character_grouping import CharacterGrouping


class CharacterIdentification:
    def __init__(self, text, title):
        # set format: {name: Character Class}
        self.title = title
        self.chars = None
        model = "en_core_web_trf"
        self.nlp = spacy.load(model)

        # load doc object
        model_path = model_saver.get_spacy_doc_path(title, doc_type=model.replace("en_core_web_", ""))
        if model_saver.exists(model_path):
            self.doc = model_saver.get_model(model_path)
            print('Pickled model exists!')
        else:
            self.doc = self.nlp(text)
            model_saver.save_model(model_path, self.doc)
            print("iPckled model didn't exist. Pickled a model.")

    def detect_characters(self):
        """
        (1) use Named Entitiy Recognition (NER) to identify person entities
        """

        chars = {}
        female_titles, male_titles = make_dataset.get_titles()
        titles = female_titles.union(male_titles)
        for i, ent in enumerate(self.doc.ents):
            if ent.label_ == "PERSON":
                # in the set, we have {name: (gender, [**index])}
                # ent is spacy.tokens.span.Span and has start attribute (index of the span in the doc)

                # print(f"ent.text: {ent.text}")
                # print(f"ent.label_: {ent.label_}")
                # print(f"ent.start: {ent.start}")
                # print(f"self.doc[ent.start-10:ent.start+10]: {self.doc[ent.start]}")
                # print("===============================================")
                name = ent.text

                # identify a title if the name has one
                if ent.start - 1 >= 0:
                    title = self.doc[ent.start - 1].text
                    title_w_o_period = title.replace(".", "")
                else:
                    title = None
                    title_w_o_period = None

                if title_w_o_period in titles:
                    name = f"{title} {name}"

                # create a dictionary index if the name does not exist in the dict yet
                # the name might have a title
                if name not in chars.keys():
                    character = Character(name)
                    chars[name] = character
                chars[name].append_occurences(ent.start)
        self.chars = chars
        return chars

    def title(self):
        pass

    def annotate_gender(self):
        """
        (2) automatically anotate a gender to each entity based on:
            (a) lists of male first names and female first names
            (b) titles such as Mr., Mrs., or Lord etc...
            (c) detecting pronouns such as him, her, his, her, himself, and herself etc...
            "a counter keeps track of counts of ‘his’ and ‘himself’ (on the one hand), and of ‘her’ and ‘herself’
            (on the other) appearing in a window of at most 3 words to the right of the name."
            https://aclanthology.org/W14-0905/
        gender options: MALE, FEMALE, UNKNOWN
        """

        """a counter keeps track of counts of ‘his’ and ‘himself’ (on the one hand), and of ‘her’ and ‘herself’
            (on the other) appearing in a win- dow of at most 3 words to the right of the name."""

        if self.chars is None:
            raise ValueError(f"self.chars has not defined yet. Run detect_characters first.")
        # initialize the GenderAnnotation class upon defining self.char
        # super().__init__(self.nlp, self.doc, self.chars)
        ga = GenderAnnotation(self.nlp, self.doc, self.chars)

        name_genders_title = ga.annotate_gender_by_titles_simple()
        print(f"_annotate_gender_by_titles_simple: "
              f"{name_genders_title}")

        name_genders_name = ga.annotate_gender_by_names()
        print(f"_annotate_gender_by_names:"
              f"{name_genders_name}")

        name_genders_pronoun = ga.annotate_gender_by_pronouns()
        print(f"_annotate_gender_by_pronouns:"
              f"{name_genders_pronoun}")

        for name in list(self.chars.keys()):
            gender_t = name_genders_title[name]
            gender_n = name_genders_name[name]
            gender_p = name_genders_pronoun[name]

            genders = [gender_t, gender_n]
            size = len(genders)
            size -= genders.count("UNKNOWN")
            print(name, size, gender_p)

            # the pronoun approach is quite unstable
            # use the pronoun approach only if the first two gender approaches cannot identify a gender

            # if all the genders in the list are UNKNOWN
            if size == 0:
                self.chars[name].update_gender(gender_p)
            # if all the specified genders in the list are FEMALE
            elif genders.count("FEMALE") == size:
                self.chars[name].update_gender("FEMALE")
            # if all the specified genders in the list are MALE
            elif genders.count("MALE") == size:
                self.chars[name].update_gender("MALE")
            # if the two of the elements are FEMALE and MALE or all undefined
            else:
                self.chars[name].update_gender(gender_p)
        return self.chars

    def _gender_unmatch(self, gender1, gender2):
        genders = [gender1, gender2]
        # if one of the two is unknown, true
        if genders.count("UNKNOWN") >= 1:
            return False
        # if two of them are the same
        elif genders.count("FEMALE") == 2 or genders.count("MALE") == 2:
            return False
        else:
            return True

    def unify_occurences(self) -> [tuple]:
        """
        Rules (https://aclanthology.org/D15-1088/)
        Two vertices cannot be merged if
        (1) the inferred genders of both names differ,
        (2) both names share a common surname but different first names, or
        (3) the honorific of both names differ, e.g., “Miss” and “Mrs.”
        :return: list representation of networkX nodes/edges
        """
        if self.chars is None:
            raise ValueError(f"self.chars has not defined yet. Run detect_characters first.")
        ou = OccurenceUnification(self.chars)
        referents = ou.unify_referents()

        # merge occurences
        same_chars = {}
        # check through if each referent exists in the story (or self.chars)
        chars_all = set(self.chars.keys())

        """possible to make this part faster"""
        # for each character name
        for name, ref in referents.items():
            # fetch possible referents in a form of set
            chars_potential = set(ref)
            # get the character names that exists in the story (or self.chars) out of the potential character names
            chars_present = chars_all.intersection(chars_potential)
            same_chars[name] = chars_present

        # filter referents that do not meet gender or title consistency
        to_remove = []
        for name, refs in same_chars.items():
            gender1 = self.chars[name].gender
            for ref in refs:
                # if the characters' genders do not match, they are different characters
                # UNKNOWNは許容する
                gender2 = self.chars[ref].gender
                if self._gender_unmatch(gender1, gender2):
                    to_remove.append((name, ref))

                # if both have a title, but they do not match, they are two separate characters
                title1: str = self.chars[name].name_parsed.title
                title2: str = self.chars[ref].name_parsed.title
                if (title1 != '' and title2 != '') and (title1 != title2):
                    to_remove.append((name, ref))
                # otherwise, they are the same character
        for name, ref in to_remove:
            same_chars[name].discard(ref)

        # if the same consistent referent exists in two separate characters' possible referent set,
        # prioritize the most frequent one (https://aclanthology.org/W14-0905/, https://aclanthology.org/E12-1065/)
        # {[REFERENT, REFERING NAME, COUNT]}
        repeated_referents = defaultdict(lambda: [])
        for name, refs in same_chars.items():
            for ref in refs:
                repeated_referents[ref].append(name)

        # delete unrepeated referents
        to_remove = []
        for ref, repeat in repeated_referents.items():
            if len(repeat) <= 1:
                to_remove.append(ref)
        for ref in to_remove:
            repeated_referents.pop(ref)

        # use union-find algorithm to cluster separate names to each group
        char_groups = CharacterGrouping(list(self.chars.keys()))
        for name, refs in same_chars.items():
            for ref in refs:
                # if a referent is repeated, skip it
                if ref in list(repeated_referents.keys()):
                    continue
                char_groups.unite(name, ref)

        # unite a consistent but repeated reference with the most frequent one
        for ref, names in repeated_referents.items():
            max_name = names[0]
            max_occurences = 0
            # fetch refering names of each referent and get the char name of the maximum occurences
            for name in names:
                occ = len(self.chars[name].occurences)
                if occ > max_occurences:
                    max_name = name
                    max_occurences = occ
            char_groups.unite(ref, max_name)

        # merge each pair of names if they share the same gender or their titles are consistent
        # assign a name that potentially refers to different characters to the most frequent name too
        # Mr. Holmes -> Sherlock Holmes or Mycroft Holmes -> assign Sherlock as more frequent than Mycroft
        charlist = list(self.chars.keys())
        correnspondence = defaultdict(list)

        for i, char1 in enumerate(charlist[:-1]):
            first1 = self.chars[char1].name_parsed.first
            last1 = self.chars[char1].name_parsed.last
            title1: str = self.chars[char1].name_parsed.title
            l1 = [first1, last1, title1]
            if l1.count('') >= 2:
                continue

            for char2 in charlist[i+1:]:
                first2 = self.chars[char2].name_parsed.first
                last2 = self.chars[char2].name_parsed.last
                title2: str = self.chars[char2].name_parsed.title
                l2 = [first2, last2, title2]
                if l2.count('') >= 2:
                    continue

                # if the characters' genders do not match, they are different characters
                if self.chars[char1].gender != self.chars[char2].gender:
                    continue
                # if both have a title, but they do not match, they are two separate characters
                if (title1 != '' and title2 != '') and (title1 != title2):
                    continue

                if first1 == first2 or last1 == last2:
                    correnspondence[char1].append(char2)
                    correnspondence[char2].append(char1)

        # assign a name that potentially refers to different characters to the most frequent name too
        # Mr. Holmes -> Sherlock Holmes or Mycroft Holmes -> assign Sherlock as more frequent than Mycroft
        # unite a consistent but repeated reference with the most frequent one
        for char1, char2s in correnspondence.items():
            max_name = char2s[0]
            max_occurences = 0
            # fetch refering names of each referent and get the char name of the maximum occurences
            for name in char2s:
                occ = len(self.chars[name].occurences)
                if occ > max_occurences:
                    max_name = name
                    max_occurences = occ
            char_groups.unite(char1, max_name)

        return char_groups.groups()
