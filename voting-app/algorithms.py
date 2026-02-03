from itertools import permutations

def parse_votes(votes, options):
    """Convert CSV vote rows to usable format"""
    parsed = []
    for vote in votes:
        scores = {}
        for opt in options:
            key = f"option_{opt['id']}"
            scores[opt["name"]] = int(vote.get(key, 0))
        parsed.append({"username": vote["username"], "scores": scores})
    return parsed


# ============== METHODS ==============

def score_voting(parsed_votes, option_names):
    """Simple sum of scores"""
    totals = {name: 0 for name in option_names}
    for vote in parsed_votes:
        for name, score in vote["scores"].items():
            totals[name] += score
    return sorted(totals.items(), key=lambda x: -x[1])

# ============== MAIN ENTRY ==============

def calculate_all_results(votes, options, max_score):
    """Calculate results for all voting methods"""
    if not votes or not options:
        return {}
    
    option_names = [o["name"] for o in options]
    parsed = parse_votes(votes, options)

    return {
        "score_voting": score_voting(parsed, option_names),
    }
