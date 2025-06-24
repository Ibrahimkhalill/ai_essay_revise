import re
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
import spacy
import random

# Download necessary NLTK data
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except:
    import sys
    import subprocess
    subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")

def classify_essay_type(text):
    """
    Classify the essay type based on content analysis.
    Returns the essay type ID (1: Argumentative, 2: Narrative, 3: Literary Analysis)
    """
    # Convert to lowercase for analysis
    text_lower = text.lower()
    
    # Define keywords for each essay type
    argumentative_keywords = ['argue', 'argument', 'thesis', 'evidence', 'claim', 'support', 'oppose', 
                             'counter', 'position', 'stance', 'debate', 'controversial', 'perspective']
    
    narrative_keywords = ['story', 'experience', 'personal', 'journey', 'adventure', 'character', 
                         'plot', 'setting', 'dialogue', 'scene', 'moment', 'memory', 'narrative']
    
    literary_keywords = ['novel', 'poem', 'author', 'character', 'theme', 'symbol', 'metaphor', 
                        'literary', 'text', 'analysis', 'interpret', 'meaning', 'work']
    
    # Count occurrences of keywords
    argumentative_count = sum(1 for keyword in argumentative_keywords if keyword in text_lower)
    narrative_count = sum(1 for keyword in narrative_keywords if keyword in text_lower)
    literary_count = sum(1 for keyword in literary_keywords if keyword in text_lower)
    
    # Additional checks for essay structure
    # Check for citations (common in argumentative essays)
    citation_pattern = r'$$\s*[A-Za-z]+\s*,\s*\d{4}\s*$$'
    citations = re.findall(citation_pattern, text)
    if len(citations) > 2:
        argumentative_count += 3
    
    # Check for first-person pronouns (common in narrative essays)
    first_person = ['i', 'me', 'my', 'mine', 'we', 'us', 'our', 'ours']
    first_person_count = sum(1 for word in word_tokenize(text_lower) if word in first_person)
    if first_person_count > 10:
        narrative_count += 3
    
    # Check for book titles or author names (common in literary analysis)
    title_pattern = r'"[^"]+"|\'[^\']+\'|\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'
    titles = re.findall(title_pattern, text)
    if len(titles) > 3:
        literary_count += 2
    
    # Determine the essay type based on the highest count
    counts = [argumentative_count, narrative_count, literary_count]
    max_count = max(counts)
    
    if max_count == 0:
        # If no clear indicators, default to argumentative
        return 1
    
    essay_type_id = counts.index(max_count) + 1
    return essay_type_id

def process_essay(text, essay_type, rules):
    """
    Process the essay and generate revisions based on essay type and rules.
    Returns a list of revisions and the revised text.
    """
    revisions = []
    
    # Tokenize the text into sentences
    sentences = sent_tokenize(text)
    
    # Process each sentence
    for i, sentence in enumerate(sentences):
        # Apply general grammar and style checks
        grammar_revisions = check_grammar(sentence, i)
        revisions.extend(grammar_revisions)
        
        # Apply essay-specific checks based on essay type
        if essay_type == 1:  # Argumentative
            type_revisions = check_argumentative(sentence, i)
        elif essay_type == 2:  # Narrative
            type_revisions = check_narrative(sentence, i)
        elif essay_type == 3:  # Literary Analysis
            type_revisions = check_literary_analysis(sentence, i)
        else:
            type_revisions = []
        
        revisions.extend(type_revisions)
        
        # Apply custom rules
        for rule in rules:
            rule_name = rule[0]
            rule_description = rule[1]
            rule_revisions = apply_custom_rule(sentence, i, rule_name, rule_description)
            revisions.extend(rule_revisions)
    
    # Apply the revisions to create the revised text
    revised_text = apply_revisions(text, revisions)
    
    return revisions, revised_text

def check_grammar(sentence, position):
    """Check for grammar issues in the sentence."""
    revisions = []
    
    # Process with spaCy for grammar analysis
    doc = nlp(sentence)
    
    # Check for subject-verb agreement
    for token in doc:
        if token.dep_ == "nsubj" and token.head.pos_ == "VERB":
            # Simple check for plural subject with singular verb or vice versa
            if token.tag_ == "NNS" and token.head.tag_ in ["VBZ"]:
                original = sentence
                revised = sentence.replace(token.head.text, token.head.text[:-1])
                revisions.append({
                    'original': original,
                    'revised': revised,
                    'position': position,
                    'reason': "Subject-verb agreement: plural subject requires plural verb form"
                })
    
    # Check for run-on sentences (simplified)
    if len(sentence) > 150 and sentence.count(',') > 3:
        # Find a good place to split the sentence
        split_point = sentence.rfind(',', 0, len(sentence) // 2)
        if split_point != -1:
            original = sentence
            revised = sentence[:split_point+1] + " " + sentence[split_point+1].upper() + sentence[split_point+2:]
            revisions.append({
                'original': original,
                'revised': revised,
                'position': position,
                'reason': "Run-on sentence: consider breaking into smaller sentences for clarity"
            })
    
    # Check for common grammar mistakes
    common_mistakes = {
        "its": "it's",
        "it's": "its",
        "their": "there",
        "there": "their",
        "your": "you're",
        "you're": "your",
        "affect": "effect",
        "effect": "affect",
        "then": "than",
        "than": "then"
    }
    
    for mistake, correction in common_mistakes.items():
        if f" {mistake} " in f" {sentence} ":
            # Only suggest a correction if it's likely a mistake (simplified logic)
            # In a real system, this would use context analysis
            if random.random() < 0.3:  # 30% chance to suggest a correction
                original = sentence
                revised = sentence.replace(f" {mistake} ", f" {correction} ")
                revisions.append({
                    'original': original,
                    'revised': revised,
                    'position': position,
                    'reason': f"Possible incorrect usage of '{mistake}'. Consider '{correction}' based on context."
                })
    
    return revisions

def check_argumentative(sentence, position):
    """Check for issues specific to argumentative essays."""
    revisions = []
    
    # Check for weak thesis statements
    if position < 3:  # Only check early sentences for thesis
        weak_phrases = ["i think", "i believe", "in my opinion", "i feel"]
        for phrase in weak_phrases:
            if phrase in sentence.lower():
                original = sentence
                revised = sentence.replace(phrase, "").strip()
                revisions.append({
                    'original': original,
                    'revised': revised,
                    'position': position,
                    'reason': "Weak thesis statement: avoid phrases like 'I think' or 'I believe' in academic writing"
                })
    
    # Check for informal language
    informal_words = ["stuff", "things", "a lot", "kind of", "sort of", "basically"]
    for word in informal_words:
        if f" {word} " in f" {sentence.lower()} ":
            original = sentence
            
            # Suggest replacements
            replacements = {
                "stuff": "material",
                "things": "items",
                "a lot": "significantly",
                "kind of": "somewhat",
                "sort of": "relatively",
                "basically": "essentially"
            }
            
            revised = sentence.lower().replace(f" {word} ", f" {replacements[word]} ")
            revisions.append({
                'original': original,
                'revised': revised,
                'position': position,
                'reason': f"Informal language: '{word}' is too casual for academic writing"
            })
    
    # Check for Wikipedia citations
    if "wikipedia" in sentence.lower():
        original = sentence
        revised = sentence  # Keep the same text but flag it
        revisions.append({
            'original': original,
            'revised': revised,
            'position': position,
            'reason': "Unreliable source: Wikipedia is not considered a reliable academic source"
        })
    
    return revisions

def check_narrative(sentence, position):
    """Check for issues specific to narrative essays."""
    revisions = []
    
    # Check for overuse of "said" (encourage more descriptive dialogue tags)
    if " said " in sentence.lower():
        said_count = sentence.lower().count(" said ")
        if said_count > 1:
            original = sentence
            
            # Suggest alternative dialogue tags
            dialogue_tags = ["whispered", "exclaimed", "replied", "asked", "shouted", "murmured"]
            revised = sentence
            
            for _ in range(said_count - 1):
                replacement = random.choice(dialogue_tags)
                revised = revised.lower().replace(" said ", f" {replacement} ", 1)
            
            revisions.append({
                'original': original,
                'revised': revised,
                'position': position,
                'reason': "Repetitive dialogue tags: vary your use of 'said' with more descriptive verbs"
            })
    
    # Check for lack of sensory details
    sensory_words = ["saw", "heard", "felt", "smelled", "tasted", "touch"]
    has_sensory = any(word in sentence.lower() for word in sensory_words)
    
    if not has_sensory and random.random() < 0.1:  # 10% chance to suggest adding sensory details
        original = sentence
        revised = sentence  # Keep the same text but flag it
        revisions.append({
            'original': original,
            'revised': revised,
            'position': position,
            'reason': "Consider adding sensory details to make your narrative more vivid and engaging"
        })
    
    return revisions

def check_literary_analysis(sentence, position):
    """Check for issues specific to literary analysis essays."""
    revisions = []
    
    # Check for past tense (literary analysis should use present tense)
    doc = nlp(sentence)
    past_tense_verbs = [token.text for token in doc if token.tag_ == "VBD"]
    
    if past_tense_verbs:
        original = sentence
        revised = sentence
        
        # Simple past to present conversion (would be more sophisticated in a real system)
        past_present = {
            "was": "is",
            "were": "are",
            "had": "has",
            "did": "does",
            "said": "says",
            "thought": "thinks",
            "felt": "feels",
            "went": "goes",
            "came": "comes",
            "saw": "sees",
            "looked": "looks"
        }
        
        for past, present in past_present.items():
            if f" {past} " in f" {revised.lower()} ":
                revised = revised.lower().replace(f" {past} ", f" {present} ")
        
        if original.lower() != revised:
            revisions.append({
                'original': original,
                'revised': revised,
                'position': position,
                'reason': "Use present tense for literary analysis: literary works are discussed in present tense"
            })
    
    # Check for book titles that should be italicized
    title_pattern = r'"([^"]+)"'
    titles = re.findall(title_pattern, sentence)
    
    for title in titles:
        if len(title.split()) > 2:  # Likely a book/novel title if more than 2 words
            original = sentence
            revised = sentence.replace(f'"{title}"', f'*{title}*')
            revisions.append({
                'original': original,
                'revised': revised,
                'position': position,
                'reason': "Book titles should be italicized, not in quotation marks"
            })
    
    return revisions

def apply_custom_rule(sentence, position, rule_name, rule_description):
    """Apply a custom rule defined by the admin."""
    revisions = []
    
    # This is a simplified implementation
    # In a real system, this would parse the rule description and apply it
    
    # Example: if rule is about passive voice
    if "passive voice" in rule_description.lower():
        doc = nlp(sentence)
        
        # Simple passive voice detection
        for token in doc:
            if token.dep_ == "nsubjpass":
                original = sentence
                # This is a simplified conversion and wouldn't work for all cases
                revised = sentence  # In a real system, we'd attempt to convert to active voice
                revisions.append({
                    'original': original,
                    'revised': revised,
                    'position': position,
                    'reason': f"Custom rule '{rule_name}': {rule_description}"
                })
                break
    
    # Example: if rule is about word count
    elif "word count" in rule_description.lower() and "limit" in rule_description.lower():
        words = word_tokenize(sentence)
        if len(words) > 30:  # Arbitrary threshold
            original = sentence
            revised = sentence  # In a real system, we'd suggest ways to shorten
            revisions.append({
                'original': original,
                'revised': revised,
                'position': position,
                'reason': f"Custom rule '{rule_name}': Sentence exceeds recommended word count"
            })
    
    return revisions

def apply_revisions(text, revisions):
    """Apply all revisions to the original text."""
    # This is a simplified implementation
    # In a real system, this would handle overlapping revisions and maintain formatting
    
    # Sort revisions by position
    revisions.sort(key=lambda x: x['position'])
    
    # Apply revisions (this is simplified and would need refinement)
    sentences = sent_tokenize(text)
    
    for revision in revisions:
        position = revision['position']
        if position < len(sentences):
            sentences[position] = revision['revised']
    
    # Reconstruct the text
    revised_text = ' '.join(sentences)
    
    return revised_text
