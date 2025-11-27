import re
from difflib import SequenceMatcher

# Case 1: Match list1 and list2 with filename template
def case_1_with_template(list1, list2, template):
    def extract_ID(filename, template):
        match = re.match(template, filename)
        if match:
            subject = match.group("subject")
            session = match.group("session")
            return subject, session
        return None, None

    def find_best_match(file1, list2, subject, session):
        best_match = None
        highest_score = 0
        for file2 in list2:
            if subject in file2 and session in file2:
                score = SequenceMatcher(None, file1, file2).ratio()
                if score > highest_score:
                    highest_score = score
                    best_match = file2
        return best_match

    results = []
    for file1 in list1:
        subject, session = extract_ID(file1, template)
        if subject and session:
            event_file = find_best_match(file1, list2, subject, session)
            if event_file:
                results.append({
                    "command": "load data",
                    "parameters": {
                        "data": file1,
                        "event": event_file,
                        "subject": subject,
                        "session": session,
                    },
                })
    return results

# Case 2: Match list1 and list2 and extract IDs
def case_2_without_template(list1, list2):
    def infer_ID(filename):
        match = re.match(r".*(?P<subject>\d+).*(?P<session>[TE]).*", filename)
        if match:
            subject = match.group("subject")
            session = match.group("session")
            return subject, session
        return None, None

    def find_best_match(file1, list2, subject, session):
        best_match = None
        highest_score = 0
        for file2 in list2:
            if subject in file2 and session in file2:
                score = SequenceMatcher(None, file1, file2).ratio()
                if score > highest_score:
                    highest_score = score
                    best_match = file2
        return best_match

    results = []
    for file1 in list1:
        subject, session = infer_ID(file1)
        if subject and session:
            event_file = find_best_match(file1, list2, subject, session)
            if event_file:
                results.append({
                    "command": "load data",
                    "parameters": {
                        "data": file1,
                        "event": event_file,
                        "subject": subject,
                        "session": session,
                    },
                })
    return results

# Case 3: Extract IDs from list1
def case_3_single_list(list1):
    def infer_ID(filename):
        match = re.match(r".*(?P<subject>\d+).*(?P<session>[TE]).*", filename)
        if match:
            subject = match.group("subject")
            session = match.group("session")
            return subject, session
        return None, None

    results = []
    for file1 in list1:
        subject, session = infer_ID(file1)
        if subject and session:
            results.append({
                "command": "load data",
                "parameters": {
                    "data": file1,
                    "subject": subject,
                    "session": session,
                },
            })
    return results