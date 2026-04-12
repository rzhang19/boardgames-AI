from collections import defaultdict

from .models import EventAttendance, Vote


def calculate_borda_scores(event, attendees_only=False):
    votes = Vote.objects.filter(event=event).select_related('user')

    if attendees_only:
        attendee_ids = set(
            EventAttendance.objects.filter(event=event)
            .values_list('user_id', flat=True)
        )
        votes = votes.filter(user_id__in=attendee_ids)

    user_ranks = defaultdict(list)
    for vote in votes:
        user_ranks[vote.user_id].append(vote)

    scores = defaultdict(int)
    for user_id, user_votes in user_ranks.items():
        n = len(user_votes)
        for vote in user_votes:
            scores[vote.board_game_id] += n - vote.rank + 1

    return dict(scores)
