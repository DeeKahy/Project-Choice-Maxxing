from itertools import permutations
from collections import Counter, defaultdict
from math import sqrt


def round_to_significant_digits(string, n):
    """Return string cut off at the nth significant digit."""
    count = 0
    for i, ch in enumerate(string):
        if ch.isdigit() and ch != "0":
            count += 1
            if count == n:
                return string[: i + 1]
    return string


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


def find_preferences(parsed_votes, mask=lambda x: x):
    """Returns a dict mapping pairs of candidates to the number of voters who prefer the first element to the second.
    Provide a single-argument mask to modify the candidates' representation in the mapping.
    """
    # preferences maps (A,B) to the number of voters who prefer A to B. Default is 0 via passing "int" to its constructor.
    preferences = {}
    for ballot in parsed_votes:
        scores = [(mask(key), value) for (key, value) in ballot["scores"].items()]
        for option_a, score_a in scores:
            for option_b, score_b in scores:
                if option_a != option_b:
                    if (option_a, option_b) not in preferences:
                        preferences[(option_a, option_b)] = 0
                    if score_a > score_b:
                        preferences[(option_a, option_b)] += 1
    return preferences


def schulze_method(parsed_votes, option_names):
    """Schulze/Beatpath method"""
    """
    # preferences maps (A,B) to the number of voters who prefer A to B. Everything starts at 0.
    preferences = {(A, B): 0 for A in option_names for B in option_names if A != B}

    # fill out the preferences
    for ballot in parsed_votes:
        scores = ballot["scores"].items()
        for option_a, score_a in scores:
            for option_b, score_b in scores:
                if option_a != option_b and score_a > score_b:
                    preferences[(option_a, option_b)] += 1
    """
    preferences = find_preferences(parsed_votes)

    # implementation of strongest path strength computation from https://en.wikipedia.org/wiki/Schulze_method
    path_strength = {}
    for i in option_names:
        for j in option_names:
            if i != j:
                path_strength[i, j] = preferences[i, j] - preferences[j, i]

    for k in option_names:
        for i in option_names:
            if i != k:
                for j in option_names:
                    if j != k and j != i:
                        path_strength[i, j] = max(
                            path_strength[i, j],
                            min(path_strength[i, k], path_strength[k, j]),
                        )

    # ranking maps options to the number of things they are preferred to.
    ranking = {option: 0 for option in option_names}  # highest rank is the best one
    for option_a in option_names:
        for option_b in option_names:
            if option_a != option_b:
                if (
                    path_strength[(option_a, option_b)]
                    >= path_strength[(option_b, option_a)]
                ):
                    # A is better than B
                    ranking[option_a] += 1

    return tiebreak_with_total_scores(
        parsed_votes, sorted(ranking.items(), reverse=True, key=lambda x: x[1])
    )


# TODO consider changing how equal-ranked items are weighted with regard to ranked-choice voting, such as all items with rank n splitting 1 vote between them
def borda_count(parsed_votes, option_names):
    # borda count is essentially score voting with some preprocessing of candidate scores.
    borda_votes = []
    for ballot in parsed_votes:
        # first we sort the voter's option/score-pairs by score in descending order to get a ranking
        ranking = sorted(ballot["scores"].items(), reverse=True, key=lambda x: x[1])
        for i in range(len(ranking)):
            # then we assign scores such that options are scored by the number of options minus the rank (not score!) given by the voter
            ranking[i] = (ranking[i][0], len(option_names) - (i + 1))
        # finally we use the ranking to reconstruct parsed_votes
        borda_votes.append({"username": ballot["username"], "scores": dict(ranking)})
    # and we send the new votes to score_voting
    return score_voting(borda_votes, option_names)


def tiebreak_with_total_scores(parsed_votes, ranked_items):
    """Sort a list of ranked voting options using the total score given to them by voters."""
    total_scores = {}
    for ballot in parsed_votes:
        scores = ballot["scores"].items()
        for option, score in scores:
            total_scores[option] = total_scores.get(option, 0) + score
    return sorted(
        ranked_items, reverse=True, key=lambda x: (x[1], total_scores.get(x[0], 0))
    )


# am using this bad boy to test frontend.
def score_voting(parsed_votes, option_names):
    """Simple sum of scores"""
    totals = {name: 0 for name in option_names}
    for vote in parsed_votes:
        for name, score in vote["scores"].items():
            totals[name] += score
    return sorted(totals.items(), reverse=True, key=lambda x: x[1])


def star_voting(parsed_votes, option_names):
    """Score Then Automatic Runoff (STAR) method"""
    # this method sorts candidates by total score, then considers the top two candidates to find a winner
    # We already have a method to rank candidates by score, so we'll use that
    options = score_voting(parsed_votes, option_names)
    ranking = []
    for _ in range(len(options) - 1):
        # out of the top two options, the winner is the one with the higher score on the most ballots
        A, _ = options[0]
        B, _ = options[1]
        A_wins = 0
        B_wins = 0
        for ballot in parsed_votes:
            if ballot["scores"][A] > ballot["scores"][B]:
                A_wins += 1
            elif ballot["scores"][A] < ballot["scores"][B]:
                B_wins += 1
        if A_wins >= B_wins:
            # add the winner to the final ranking and remove it from the options to give the others a chance
            del options[0]
            ranking.append((A, A_wins))
            if len(options) == 1:
                # put the other option at the end so it's included even if it never won, if it's the only one left
                ranking.append((B, B_wins))
        else:
            del options[1]
            ranking.append((B, B_wins))
            if len(options) == 1:
                ranking.append((A, A_wins))
    return ranking


def kemeny_young(parsed_votes, option_names, brute_force=False):
    """Kemeny-Young rule/Kemeny method. Set brute_force=True to verify the result using brute-force."""
    # Gonna be lots of comments in this one. Based it on a math paper so steel yourself.
    preferences = find_preferences(parsed_votes, mask=option_names.index)
    # With the preferences known, we now have to find the sequence of candidates that satisfies the most voters' preferences.
    # This is NP-hard and slow and awful no matter what, especially with more candidates.

    # One sub-exponential solution to this problem requires us to sort the candidates by weighted indegree in increasing order.
    # Weights (preference counts) are normalized such that preferences[(A, B)] + preferences[(B, A)] = 1.
    preferences = {
        (A, B): (
            preferences[(A, B)]
            / (1, preferences[(A, B)] + preferences[(B, A)])[
                (preferences[(A, B)] + preferences[(B, A)]) != 0
            ]
        )
        for (A, B) in list(preferences)
    }
    print("Preferences normalized:")
    for A, B in preferences:
        if preferences[(A, B)] >= preferences[(B, A)]:
            print(f"{A} is preferred to {B} by {preferences[(A, B)]}")
    # V will stand in for option_names to ensure deterministic behaviour (hashes of strings change with each run!).
    V = list(range(len(option_names)))
    # For us, sorting by weighted indegree means sorting by the sum of preferences for each candidate, which gets us the following ranking:
    π1 = sorted(
        V,
        key=lambda v: sum([preferences[(v, u)] for u in V if v != u]),
        reverse=True,
    )
    # We'll also need some helper functions for this job:
    # C is our cost function and computes the weight of the preferences we don't fulfill (the backwards arcs in a graph of candiates with preferences as edges)
    C = lambda π: sum(preferences[(u, v)] for i, v in enumerate(π) for u in π[i + 1 :])
    print(f"Initial ranking is ->{π1} with cost {C(π1)}")
    # b computes the weight of the arcs incident to v in the ordering formed by moving v to position p in π.
    b = lambda π, v, p: sum(
        (preferences[(u, v)], preferences[(v, u)])[p > π.index(u)]
        for u in V
        if u != v and p != π.index(u)
    )
    # r defines the uncertainty of each candidate's placement in the ranking.
    r = {v: (4 * sqrt(2 * C(π1))) + (2 * b(π1, v, π1.index(v))) for v in V}
    print("Uncertainties computed:")
    for i, v in enumerate(V):
        print(
            f"r({v}) = {r[v]}",
            end=("\t" if i != len(V) - 1 else "\n"),
        )
    # We need to find a new ranking π2 such that |π2(v) − π1(v)| ≤ r(v) for all v.
    # Dynamic programming will allow us to do that. But first we need to compute a kernel, to actually achieve our desired performance.
    # The kernel is computed with a majority tournament, which is an unweighted graph of all the majority preferences:
    mt = [
        (A, B) for (A, B) in preferences if preferences[(A, B)] <= preferences[(B, A)]
    ]  # mt is a list of pairs where there's an arc from the first to the second item.
    print(
        f"Majority tournament constructed with {len(V)} vertices and {len(mt)} edges."
    )
    # We need to break ties in mt so arcs never go both ways between two vertices:
    tied = True
    while tied:
        tied = False
        for A, B in mt:
            if (B, A) in mt:
                mt.remove((B, A))
                tied = True
                break
    print(
        f"Tiebreaking completed with {len(mt)} {"edges" if len(mt)!=1 else "edge"} remaining."
    )
    # We apply reduction rules to compute the kernel. The first rule removes any vertex that is not part of a triangle (3-arc cycle)
    # The second rule concerns arcs that are present in more than 2U triangles, so let's get some triangles.
    triangles = lambda mt: {
        frozenset((a, b, c)) for a, b in mt for c in V if (b, c) in mt and (c, a) in mt
    }
    in_triangle = lambda v, ts: any(v in t for t in ts)
    in_triangles = lambda v, u, ts: sum((v in t and u in t) for t in ts if (v, u) in mt)
    mt_cost = lambda mt: sum(preferences[(A, B)] for (A, B) in mt)
    # U will be somewhere between the optimal cost and 5 times the optimal cost.
    # At the end of kernelization it should be equal to the initial cost C(π1),
    # which indicates that the kernel is a more compact version of our existing problem, as intended.
    U = C(π1)
    must_pay = 0
    trivial = []  # [(vertex, predecessor set, successor set)]
    while True:
        ts = triangles(mt)
        # First reduction rule: Eliminate vertices that aren't part of a triangle. These are trivial to insert into the ranking.
        # Record their immediate predecessors and successors. We will use those to insert them into the ranking later.
        triangle_free = [v for v in V if not in_triangle(v, ts)]
        trivial += [
            (v, {A for (A, B) in mt if B == v}, {B for (A, B) in mt if A == v})
            for v in triangle_free
        ]
        # Note that we remember the cost of including trivial vertices, since we still have to pay for them later.
        if triangle_free:
            print(
                f"Kernelization found {len(triangle_free)} trivial {"vertices" if len(triangle_free)!=1 else "vertex"}."
            )
            must_pay += mt_cost(mt)
            mt = [e for e in mt for v in triangle_free if v not in e]
            must_pay -= mt_cost(mt)
            for v in triangle_free:
                # v can be trivially ranked so we can remove it from V to make the dynamic programming-part run faster.
                V.remove(v)

        # Second reduction rule: Flip edges that are in more than 2U triangles and set their weight to 1, and always add their original weight to U.
        flipped = [(A, B) for (A, B) in mt if in_triangles(A, B, ts) > (2 * U)]
        mt = [(B, A) if (A, B) in flipped else (A, B) for (A, B) in mt]
        for A, B in flipped:
            # Note that (A,B) from mt is (B,A) in preferences. Might want to homogenize that at some point.
            must_pay += preferences[(B, A)]
            preferences[(B, A)] = 0
            preferences[(A, B)] = 1
        if flipped:
            print(
                f"Kernelization flipped and hardened {len(flipped)} {"edges that were" if len(flipped)!=1 else "edge that was"} in more than 2*U ({2*U}) triangles."
            )
        if not (flipped or triangle_free):
            break  # Break the loop if we didn't flip any edges or eliminate any vertices.

    # Now we've modified weights to make our life easier and saved trivial vertices for later.
    if trivial:
        print(f"The following vertices are trivial:")
        for v, p, s in trivial:
            print(
                f"'{v}' comes after {p if p else "nothing"} and before {s if s else "nothing"}{" (first place in ranking)" if not s else " (last place in ranking)" if not p  else ""}."
            )
    if U < mt_cost(mt) + must_pay:
        raise RuntimeError(  # Kernel cost must not be greater than the initial cost, or the kernel is invalid!
            f"Sanity check failed: Kernel cost {mt_cost(mt) + must_pay} is greater than initial cost {C(π1)}"
        )
    # It's time for dynamic programming so we can find our optimal ranking π2.
    valid = lambda S: (
        all(v in S for v in V if (π1.index(v) <= (len(S) - r[v])))
        and all(v not in S for v in V if (π1.index(v) > (len(S) + r[v])))
    )
    # subset_cost handles our memoization. Cbar computes the optimal cost of ranking the candidates in set S.
    subset_cost = {}
    Cbar = lambda S: subset_cost.setdefault(
        S,
        min(
            [
                (Cbar(S - {v}) + sum(preferences[(u, v)] for u in S - {v}))
                for v in S
                if valid(S - {v})
            ],
            default=0,
        ),
    )
    # We can fill out subset_cost by giving Cbar the full set of candidates we want to rank.
    # (We use a frozenset because it is immutable and thus hashable)
    π2 = []
    T = frozenset(V)
    while len(T):  # Loop while there are candidates left.
        # Find the candidate that is cheapest to place last and append it.
        for v in T:
            if valid(T - {v}) and Cbar(T) == (
                Cbar(T - {v}) + sum(preferences[(u, v)] for u in T - {v})
            ):
                π2.append(v)
                T -= {v}
                break
    if V:
        print(f"Optimal subset ranking costs computed:")
        for i, s in enumerate(subset_cost):
            print(
                f"Cbar({set(s) if s else "Ø"}) = {subset_cost[s]}",
                end=("\t" if i != len(subset_cost) - 1 else "\n"),
            )
    print(f"Non-trivial ranking is ->{π2}")

    # Now we have ranked the non-trivial candidates. It's time to insert the trivial ones.
    for v, p, s in trivial:
        # v should come after all its predecessors and before all its successors. (Predecessors being vertices lower in the ranking)
        max_s = max(map(π2.index, s & set(π2)), default=0)
        min_p = min(map(π2.index, p & set(π2)), default=len(π2))
        if min_p < max_s:
            raise RuntimeError(  # No predecessor may come after a successor! This is a sign that the non-trivial part has gone wrong.
                f"Sanity check failed: Predecessors {p} and successors {s} overlap in ranking {π2}."
            )
        π2.insert(min_p, v)
    print(f"Final ranking is ->{π2} with cost {C(π2)}")
    if brute_force and (cost := KY_brute_force(option_names, C)) != C(π2):
        raise RuntimeError(  # The solution should have the same cost as the optimal brute-force solution.
            f"Sanity check failed: Final cost {C(π2)} does not agree with brute-force optimal cost {cost}"
        )
    return [(option_names[v], C(π2[i:])) for i, v in enumerate(π2)]


def KY_brute_force(option_names, C):
    """Brute-force optimal cost of the Kemeny-Young method.\n
    Do not, under any circumstances, use this for anything other than testing."""
    optimal_solutions = []
    optimal_cost = len(option_names)
    print("Starting brute-force attempt.")
    for π in permutations(range(len(option_names))):
        if (cost := C(π)) < optimal_cost:
            optimal_solutions = [π]
            optimal_cost = cost
        elif cost == optimal_cost:
            optimal_solutions.append(π)
    print(f"Brute-force finds the following rankings with optimal cost {optimal_cost}:")
    for π in optimal_solutions:
        print(f"->{list(π)}")
    return optimal_cost


# ============== MAIN ENTRY ==============


def calculate_all_results(votes, options, max_score):
    """Calculate results for all voting methods"""
    if not votes or not options:
        return {}

    option_names = [o["name"] for o in options]
    parsed = parse_votes(votes, options)

    return {
        "score_voting": score_voting(parsed, option_names),
        "schulze_method": schulze_method(parsed, option_names),
        "borda_count": borda_count(parsed, option_names),
        "star_voting": star_voting(parsed, option_names),
        "kemeny_young": [
            (k, round_to_significant_digits(str(v), 3))
            for (k, v) in kemeny_young(parsed, option_names)
        ],
    }
