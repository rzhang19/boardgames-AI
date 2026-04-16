from datetime import datetime, time as dt_time

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.signing import TimestampSigner
from django.forms import formset_factory, modelformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .bgg import fetch_bgg_game, search_bgg
from .borda import calculate_borda_scores
from .forms import (
    BetaAccessForm, BoardGameForm, EventForm, SetPasswordForm, SettingsForm,
    UserAddForm, UserManageForm, RegistrationForm, VoteForm,
)
from .models import BoardGame, Event, EventAttendance, Vote
from .timezone_utils import is_valid_timezone

User = get_user_model()


def site_admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/login/')
        if not (request.user.is_superuser or request.user.is_site_admin):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_manage_queryset(request):
    qs = User.objects.all()
    if not request.user.is_superuser:
        qs = qs.exclude(is_site_admin=True)
    return qs


@site_admin_required
def manage_users(request):
    if 'cancel' in request.POST:
        return redirect('dashboard')

    queryset = _get_manage_queryset(request)

    UserFormSet = modelformset_factory(
        User,
        form=UserManageForm,
        extra=0,
    )

    if request.method == 'POST':
        formset = UserFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            changes = {}
            for form in formset:
                if form.has_changed():
                    user_obj = form.instance
                    changes[str(user_obj.pk)] = {
                        'is_organizer': form.cleaned_data.get('is_organizer', False),
                        'is_site_admin': form.cleaned_data.get('is_site_admin', False),
                    }

            if not changes:
                formset = UserFormSet(queryset=queryset)
                return render(request, 'club/manage_users.html', {
                    'formset': formset,
                    'no_changes': True,
                    'is_superuser': request.user.is_superuser,
                })

            promote_organizer_ids = []
            demote_organizer_ids = []
            promote_site_admin_ids = []
            demote_site_admin_ids = []

            for uid, role_changes in changes.items():
                user = User.objects.get(pk=uid)
                if user.is_organizer != role_changes['is_organizer']:
                    if role_changes['is_organizer']:
                        promote_organizer_ids.append(uid)
                    else:
                        demote_organizer_ids.append(uid)
                if user.is_site_admin != role_changes['is_site_admin']:
                    if role_changes['is_site_admin']:
                        promote_site_admin_ids.append(uid)
                    else:
                        demote_site_admin_ids.append(uid)

            request.session['pending_role_changes'] = changes

            return render(request, 'club/manage_users_confirm.html', {
                'promote_organizer_users': User.objects.filter(pk__in=promote_organizer_ids),
                'demote_organizer_users': User.objects.filter(pk__in=demote_organizer_ids),
                'promote_site_admin_users': User.objects.filter(pk__in=promote_site_admin_ids),
                'demote_site_admin_users': User.objects.filter(pk__in=demote_site_admin_ids),
            })
    else:
        formset = UserFormSet(queryset=queryset)

    return render(request, 'club/manage_users.html', {
        'formset': formset,
        'is_superuser': request.user.is_superuser,
    })


@site_admin_required
def manage_users_confirm(request):
    if request.method != 'POST':
        return redirect('manage_users')

    changes = request.session.pop('pending_role_changes', {})

    if not request.user.is_superuser:
        site_admin_ids = set(
            User.objects.filter(is_site_admin=True).values_list('pk', flat=True)
        )
        changes = {
            uid: role_changes
            for uid, role_changes in changes.items()
            if int(uid) not in site_admin_ids
        }

    for user_id, role_changes in changes.items():
        User.objects.filter(pk=user_id).update(**role_changes)

    return redirect('manage_users')


@site_admin_required
def manage_users_cancel(request):
    request.session.pop('pending_role_changes', None)
    return redirect('manage_users')


@site_admin_required
def user_add(request):
    if request.method == 'POST':
        form = UserAddForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_unusable_password()
            user.email_verified = False
            user.save()
            signer = TimestampSigner()
            token = signer.sign(user.pk)
            set_pw_url = request.build_absolute_uri(f'/set-password/{token}/')
            send_mail(
                'Set your password - Board Game Club',
                f'An account has been created for you. Set your password here: {set_pw_url}',
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )
            return redirect('manage_users')
    else:
        form = UserAddForm()
    return render(request, 'club/manage_users_add.html', {'form': form})


@site_admin_required
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.is_superuser or user.pk == request.user.pk:
        raise PermissionDenied
    if request.method == 'POST':
        user.delete()
        return redirect('manage_users')
    return render(request, 'club/manage_users_delete.html', {'target_user': user})


def user_set_password(request, token):
    signer = TimestampSigner()
    try:
        user_pk = signer.unsign(token, max_age=86400 * 3)
    except Exception:
        return render(request, 'registration/set_password.html', {
            'form': None,
            'invalid_token': True,
        })

    user = get_object_or_404(User, pk=user_pk)

    if request.method == 'POST':
        form = SetPasswordForm(request.POST)
        if form.is_valid():
            user.password = make_password(form.cleaned_data['new_password1'])
            user.email_verified = True
            user.save()
            return render(request, 'registration/set_password.html', {
                'form': None,
                'success': True,
            })
    else:
        form = SetPasswordForm()

    return render(request, 'registration/set_password.html', {
        'form': form,
        'invalid_token': False,
    })


def beta_access(request):
    beta_hash = getattr(settings, 'BETA_ACCESS_CODE_HASH', '')
    if not beta_hash:
        return redirect('dashboard')

    if request.method == 'POST':
        form = BetaAccessForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['access_code']
            if check_password(code, beta_hash):
                response = redirect('dashboard')
                signer = TimestampSigner()
                signed = signer.sign('granted')
                response.set_cookie(
                    'beta_access',
                    signed,
                    max_age=90 * 86400,
                    httponly=True,
                    secure=not settings.DEBUG,
                    samesite='Lax',
                )
                return response
            form.add_error('access_code', 'Invalid access code.')
    else:
        form = BetaAccessForm()

    return render(request, 'club/beta_access.html', {'form': form})


def dashboard(request):
    return render(request, 'club/dashboard.html')


def user_settings(request):
    if not request.user.is_authenticated:
        return redirect('/login/')

    if request.method == 'POST':
        form = SettingsForm(request.POST)
        if form.is_valid():
            new_email = form.cleaned_data['email']
            new_tz = form.cleaned_data['timezone']
            user = request.user

            email_changed = new_email != user.email
            tz_changed = new_tz != user.timezone

            if email_changed:
                user.email = new_email
                if new_email:
                    user.email_verified = False
                else:
                    user.email_verified = False

            if tz_changed:
                user.timezone = new_tz
                user.timezone_detected = False

            if email_changed or tz_changed:
                user.save()
                if email_changed and new_email:
                    signer = TimestampSigner()
                    token = signer.sign(user.pk)
                    verify_url = request.build_absolute_uri(f'/verify-email/{token}/')
                    send_mail(
                        'Verify your email - Board Game Club',
                        f'Click the link to verify your email: {verify_url}',
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                    )
            return redirect('user_settings')
    else:
        form = SettingsForm(initial={
            'email': request.user.email,
            'timezone': request.user.timezone or 'UTC',
        })

    return render(request, 'club/settings.html', {'form': form})


def save_timezone(request):
    if request.method != 'POST':
        return redirect('dashboard')
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.user.timezone_detected:
        return redirect('dashboard')

    tz_name = request.POST.get('timezone', '')
    if is_valid_timezone(tz_name):
        request.user.timezone = tz_name
        request.user.timezone_detected = True
        request.user.save(update_fields=['timezone', 'timezone_detected'])
    return redirect(request.POST.get('next', 'dashboard'))


def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            if not user.email:
                user.email_verified = False
                user.save()
                login(request, user)
                return redirect('dashboard')
            if settings.REQUIRE_EMAIL_VERIFICATION:
                signer = TimestampSigner()
                token = signer.sign(user.pk)
                verify_url = request.build_absolute_uri(f'/verify-email/{token}/')
                send_mail(
                    'Verify your email - Board Game Club',
                    f'Click the link to verify your email: {verify_url}',
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                )
                return render(request, 'registration/verify_email_sent.html', {'email': user.email})
            else:
                user.email_verified = True
                user.save()
                login(request, user)
                return redirect('dashboard')
    else:
        form = RegistrationForm()
    return render(request, 'registration/register.html', {'form': form})


def verify_email(request, token):
    signer = TimestampSigner()
    try:
        user_pk = signer.unsign(token, max_age=86400)
    except Exception:
        return render(request, 'registration/verify_email_confirmed.html', {'success': False})

    user = get_object_or_404(User, pk=user_pk)
    if not user.email_verified:
        user.email_verified = True
        user.save()
    return render(request, 'registration/verify_email_confirmed.html', {'success': True})


def bgg_search(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse([], safe=False)
    results = search_bgg(query)
    return JsonResponse(results, safe=False)


def bgg_import(request, bgg_id):
    if not request.user.is_authenticated:
        return redirect('/login/')
    data = fetch_bgg_game(bgg_id)
    if data is None:
        return JsonResponse({'error': 'Game not found on BoardGameGeek'})
    return JsonResponse(data)


def game_list(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    games = BoardGame.objects.select_related('owner').all()
    return render(request, 'club/game_list.html', {'games': games})


def game_add(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.method == 'POST':
        form = BoardGameForm(request.POST)
        if form.is_valid():
            game = form.save(commit=False)
            game.owner = request.user
            bgg_id = form.cleaned_data.get('bgg_id')
            if bgg_id:
                bgg_data = fetch_bgg_game(bgg_id)
                if bgg_data:
                    game.bgg_id = bgg_data['bgg_id']
                    game.bgg_link = bgg_data['bgg_link']
                    game.image_url = bgg_data['image_url'] or ''
                    game.bgg_last_synced = timezone.now()
            game.save()
            return redirect('game_detail', pk=game.pk)
    else:
        form = BoardGameForm()
    return render(request, 'club/game_form.html', {'form': form, 'action': 'Add'})


def game_detail(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    game = get_object_or_404(BoardGame, pk=pk)
    return render(request, 'club/game_detail.html', {'game': game})


def game_edit(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    game = get_object_or_404(BoardGame, pk=pk)
    if game.owner != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        form = BoardGameForm(request.POST, instance=game)
        if form.is_valid():
            bgg_id = form.cleaned_data.get('bgg_id')
            if bgg_id:
                bgg_data = fetch_bgg_game(bgg_id)
                if bgg_data:
                    game.bgg_id = bgg_data['bgg_id']
                    game.bgg_link = bgg_data['bgg_link']
                    game.image_url = bgg_data['image_url'] or ''
                    game.bgg_last_synced = timezone.now()
            form.save()
            return redirect('game_detail', pk=game.pk)
    else:
        form = BoardGameForm(instance=game)
    return render(request, 'club/game_form.html', {'form': form, 'action': 'Edit'})


def game_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    game = get_object_or_404(BoardGame, pk=pk)
    if game.owner != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        game.delete()
        return redirect('game_list')
    return render(request, 'club/game_confirm_delete.html', {'game': game})


def event_list(request):
    events = Event.objects.select_related('created_by').all()
    return render(request, 'club/event_list.html', {
        'events': events,
        'time_midnight': dt_time(0, 0),
    })


def event_add(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not request.user.is_organizer:
        raise PermissionDenied
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.date = form.cleaned_data['date']
            event.created_by = request.user
            event.voting_deadline = form.cleaned_data.get('voting_deadline') or event.date
            event.save()
            return redirect('event_detail', pk=event.pk)
    else:
        form = EventForm()
    return render(request, 'club/event_form.html', {'form': form, 'action': 'Create'})


def event_edit(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not request.user.is_organizer:
        raise PermissionDenied
    event = get_object_or_404(Event, pk=pk)
    old_date = event.date
    old_deadline = event.voting_deadline
    old_gap = old_date - old_deadline if old_deadline else None

    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            event = form.save(commit=False)
            event.date = form.cleaned_data['date']
            new_deadline = form.cleaned_data.get('voting_deadline')
            date_changed = (
                event.date.date() != old_date.date()
                or event.date.hour != old_date.hour
                or event.date.minute != old_date.minute
            )

            if new_deadline:
                event.voting_deadline = new_deadline
            elif date_changed and old_gap and old_deadline != old_date:
                event.voting_deadline = event.date - old_gap
            else:
                event.voting_deadline = event.date

            event.save()
            return redirect('event_detail', pk=event.pk)
    else:
        form = EventForm(instance=event)
    return render(request, 'club/event_form.html', {'form': form, 'action': 'Edit'})


def event_vote(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not EventAttendance.objects.filter(user=request.user, event=event).exists():
        raise PermissionDenied

    event.sync_voting_status()
    event.refresh_from_db()

    games = BoardGame.objects.all()

    existing_votes = Vote.objects.filter(
        user=request.user, event=event
    ).select_related('board_game')
    vote_data = []
    for vote in existing_votes:
        vote_data.append({'board_game': vote.board_game_id, 'rank': vote.rank, 'game_name': vote.board_game.name})

    if not event.is_voting_open:
        if request.method == 'POST':
            return render(request, 'club/event_vote.html', {
                'event': event,
                'formset': None,
                'games': games,
                'vote_data': vote_data,
                'voting_closed': True,
                'mid_submit_closed': True,
            })

        VoteFormSet = formset_factory(VoteForm, extra=0)
        formset = VoteFormSet(initial=vote_data)
        return render(request, 'club/event_vote.html', {
            'event': event,
            'formset': formset,
            'games': games,
            'vote_data': vote_data,
            'voting_closed': True,
            'mid_submit_closed': False,
        })

    if request.method == 'POST':
        Vote.objects.filter(user=request.user, event=event).delete()

        total_forms = int(request.POST.get('form-TOTAL_FORMS', '0'))
        for i in range(total_forms):
            game_id = request.POST.get(f'form-{i}-board_game', '')
            rank = request.POST.get(f'form-{i}-rank', '')
            if game_id and rank:
                Vote.objects.create(
                    user=request.user,
                    event=event,
                    board_game_id=int(game_id),
                    rank=int(rank),
                )
        return redirect('event_detail', pk=event.pk)

    VoteFormSet = formset_factory(VoteForm, extra=max(0, 3 - len(vote_data)))
    initial = vote_data if vote_data else []
    formset = VoteFormSet(initial=initial)

    return render(request, 'club/event_vote.html', {
        'event': event,
        'formset': formset,
        'games': games,
        'voting_closed': False,
        'mid_submit_closed': False,
    })


def event_results(request, pk):
    event = get_object_or_404(Event, pk=pk)
    scores = calculate_borda_scores(event)
    game_map = {g.pk: g for g in BoardGame.objects.filter(pk__in=scores.keys())}

    results = []
    for game_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        results.append({
            'game': game_map[game_id],
            'score': score,
        })

    show_individual = event.show_individual_votes
    individual_votes = None
    if show_individual:
        attendee_ids = EventAttendance.objects.filter(
            event=event
        ).values_list('user_id', flat=True)
        votes = Vote.objects.filter(
            event=event, user_id__in=attendee_ids
        ).select_related('user', 'board_game').order_by('user', 'rank')
        user_votes = {}
        for vote in votes:
            user_votes.setdefault(vote.user, []).append(vote)
        individual_votes = user_votes

    return render(request, 'club/event_results.html', {
        'event': event,
        'results': results,
        'show_individual': show_individual,
        'individual_votes': individual_votes,
    })


def event_toggle_visibility(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not request.user.is_organizer:
        raise PermissionDenied
    event = get_object_or_404(Event, pk=pk)
    event.show_individual_votes = not event.show_individual_votes
    event.save()
    return redirect('event_detail', pk=event.pk)


def event_toggle_voting(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not request.user.is_organizer:
        raise PermissionDenied
    event = get_object_or_404(Event, pk=pk)
    event.sync_voting_status()
    event.refresh_from_db()

    if event.is_voting_open:
        event.voting_open = False
        event.save()
    else:
        if not event.is_active:
            return redirect('event_detail', pk=event.pk)
        if timezone.now() >= event.voting_deadline:
            return redirect('event_detail', pk=event.pk)
        event.voting_open = True
        event.save()

    return redirect('event_detail', pk=event.pk)


def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    event.sync_voting_status()
    event.refresh_from_db()
    attendees = EventAttendance.objects.filter(event=event).select_related('user')
    is_attending = False
    if request.user.is_authenticated:
        is_attending = EventAttendance.objects.filter(
            user=request.user, event=event
        ).exists()
    can_resume = (
        not event.voting_open
        and event.is_currently_active
        and timezone.now() < event.voting_deadline
    )
    return render(request, 'club/event_detail.html', {
        'event': event,
        'attendees': attendees,
        'is_attending': is_attending,
        'time_midnight': dt_time(0, 0),
        'can_resume': can_resume,
    })


def event_rsvp(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    attendance = EventAttendance.objects.filter(
        user=request.user, event=event
    )
    if attendance.exists():
        attendance.delete()
    else:
        EventAttendance.objects.create(user=request.user, event=event)
    return redirect('event_detail', pk=event.pk)
