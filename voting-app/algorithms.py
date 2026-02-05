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

def schulze_method(parsed_votes, option_names):
    """Schulze/Beatpath method"""
    # preferences maps (A,B) to the number of voters who prefer A to B. Everything starts at 0.
    preferences = {(A,B) : 0 for A in option_names for B in option_names if A != B}
    
    # fill out the preferences
    for dict in parsed_votes:
        # username = dict["username"]
        scores = dict["scores"].items()
        for option_a, score_a in scores:
            for option_b, score_b in scores:
                if option_a != option_b and score_a > score_b:
                    preferences[(option_a,option_b)] += 1

    # implementation of strongest path strength computation from https://en.wikipedia.org/wiki/Schulze_method
    path_strength = {}
    for i in option_names:
        for j in option_names:
            if i != j:
                path_strength[i,j] = preferences[i,j] - preferences[j,i]

    for k in option_names:
        for i in option_names:
            if i != k:
                for j in option_names:
                    if j != k and j != i:
                        path_strength[i,j] = max(path_strength[i,j], min(path_strength[i,k], path_strength[k,j]))
                        
    # ranking maps options to the number of things they are preferred to.
    ranking = {option : 0 for option in option_names}  # highest rank is the best one
    for option_a in option_names:
        for option_b in option_names:
            if option_a != option_b:
                if path_strength[(option_a,option_b)] >= path_strength[(option_b,option_a)]:
                    # A is better than B
                    ranking[option_a] += 1

    return tiebreak_with_total_scores(parsed_votes, sorted(ranking.items(), reverse=True, key=lambda x: x[1]))
    
def tiebreak_with_total_scores(parsed_votes, ranked_items):
    """Sort a list of ranked voting options using the total score given to them by voters."""
    total_scores = {}
    for dict in parsed_votes:
        scores = dict["scores"].items()
        for option, score in scores:
            total_scores[option] = total_scores.get(option, 0) + score
    return sorted(ranked_items, reverse=True, key=lambda x: (x[1], total_scores.get(x[0], 0)))

# am using this bad boy to test frontend.
def score_voting(parsed_votes, option_names):
    """Simple sum of scores"""
    totals = {name: 0 for name in option_names}
    for vote in parsed_votes:
        for name, score in vote["scores"].items():
            totals[name] += score
    return sorted(totals.items(), reverse=True, key=lambda x: x[1])

# ============== MAIN ENTRY ==============

def calculate_all_results(votes, options, max_score):
    """Calculate results for all voting methods"""
    if not votes or not options:
        return {}
    
    option_names = [o["name"] for o in options]
    parsed = parse_votes(votes, options)

    return {
        "score_voting": score_voting(parsed, option_names),
        "schulze_method" : schulze_method(parsed, option_names)
    }
