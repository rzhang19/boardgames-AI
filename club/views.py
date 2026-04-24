from datetime import datetime, time as dt_time

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.signing import TimestampSigner
from django.db.models import Q
from django.forms import formset_factory, modelformset_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .bgg import fetch_bgg_game, fetch_bgg_weight, search_bgg, weight_to_complexity
from .borda import calculate_borda_scores
from .forms import (
    BetaAccessForm, BoardGameForm, EventForm, GroupCreateForm, GroupSettingsForm,
    RecurringEventForm, SetPasswordForm, SettingsForm, SuccessorPickForm,
    UserAddForm, UserManageForm, RegistrationForm, VerifiedIconForm, VoteForm,
)
from .models import BoardGame, Event, EventAttendance, Group, GroupCreationLog, GroupInvite, GroupJoinRequest, GroupMembership, Notification, SiteSettings, VerifiedIcon, Vote
from .notifications import (
    generate_missing_complexity_notifications,
    generate_missing_max_players_notifications,
    notify_group_demoted_member,
    notify_group_demoted_organizer,
    notify_group_event_created,
    notify_group_event_updated,
    notify_group_grace_period,
    notify_group_invite_created,
    notify_group_join_approved,
    notify_group_join_rejected,
    notify_group_member_joined,
    notify_group_member_left,
    notify_group_join_request,
    notify_group_promoted_admin,
    notify_group_promoted_organizer,
    notify_group_removed,
    notify_group_restored,
    notify_group_settings_changed,
    notify_group_voting_ended,
    notify_group_voting_resumed,
)
from .permissions import (
    can_create_event,
    can_create_group,
    can_delete_group,
    can_edit_group_settings,
    can_restore_group,
    can_view_group,
    is_group_admin,
    is_group_member,
    is_group_organizer,
)
from .timezone_utils import is_valid_timezone
from .utils import parse_bgg_link, resize_group_image, resize_profile_picture

User = get_user_model()


def _process_bgg_link(game, form):
    bgg_id = form.cleaned_data.get('bgg_id')
    bgg_link_input = form.cleaned_data.get('bgg_link_input', '')

    if bgg_id:
        bgg_data = fetch_bgg_game(bgg_id)
        if bgg_data:
            game.bgg_id = bgg_data['bgg_id']
            game.bgg_link = bgg_data['bgg_link']
            game.image_url = bgg_data.get('image_url') or ''
            game.bgg_last_synced = timezone.now()
        weight = fetch_bgg_weight(bgg_id)
        if weight is not None:
            game.bgg_weight = weight
            if not game.complexity:
                game.complexity = weight_to_complexity(weight)
    elif bgg_link_input and bgg_link_input.strip():
        parsed = parse_bgg_link(bgg_link_input)
        if parsed:
            game.bgg_id = parsed['bgg_id']
            game.bgg_link = parsed['bgg_link']
            bgg_data = fetch_bgg_game(parsed['bgg_id'])
            if bgg_data:
                game.bgg_link = bgg_data['bgg_link'] or game.bgg_link
                game.image_url = bgg_data.get('image_url') or ''
                game.bgg_last_synced = timezone.now()
            weight = fetch_bgg_weight(parsed['bgg_id'])
            if weight is not None:
                game.bgg_weight = weight
                if not game.complexity:
                    game.complexity = weight_to_complexity(weight)
    else:
        game.bgg_id = None
        game.bgg_link = ''
        game.image_url = ''
        game.bgg_weight = None
        game.bgg_last_synced = None


class CustomLoginView(auth_views.LoginView):
    def form_valid(self, form):
        response = super().form_valid(form)
        generate_missing_complexity_notifications(self.request.user)
        generate_missing_max_players_notifications(self.request.user)
        return response


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
                        'is_site_admin': form.cleaned_data.get('is_site_admin', False),
                    }

            promote_site_admin_ids = []
            demote_site_admin_ids = []
            actual_changes = {}

            for uid, role_changes in changes.items():
                user = User.objects.get(pk=uid)
                if user.is_site_admin == role_changes['is_site_admin']:
                    continue
                actual_changes[uid] = role_changes
                if role_changes['is_site_admin']:
                    promote_site_admin_ids.append(uid)
                else:
                    demote_site_admin_ids.append(uid)

            if not actual_changes:
                formset = UserFormSet(queryset=queryset)
                return render(request, 'club/manage_users.html', {
                    'formset': formset,
                    'no_changes': True,
                    'is_superuser': request.user.is_superuser,
                })

            request.session['pending_role_changes'] = actual_changes

            return render(request, 'club/manage_users_confirm.html', {
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
            temp_pw = form.cleaned_data.get('temporary_password')
            if temp_pw:
                user.set_password(temp_pw)
                user.must_change_password = True
            else:
                user.set_unusable_password()
            user.email_verified = False
            user.save()
            if user.email:
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
        confirm_username = request.POST.get('confirm_username', '').strip()
        if confirm_username != user.username:
            return render(request, 'club/manage_users_delete.html', {
                'target_user': user,
                'error': True,
            })
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


def forced_password_change(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not request.user.must_change_password:
        return redirect('dashboard')

    if request.method == 'POST':
        form = SetPasswordForm(request.POST)
        if form.is_valid():
            new_pw = form.cleaned_data['new_password1']
            if check_password(new_pw, request.user.password):
                form.add_error(
                    'new_password1',
                    'Your new password must be different from your temporary password.',
                )
            else:
                request.user.set_password(new_pw)
                request.user.must_change_password = False
                request.user.save()
                login(request, request.user)
                return redirect('dashboard')
    else:
        form = SetPasswordForm()

    return render(request, 'club/forced_password_change.html', {'form': form})


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
    if not request.user.is_authenticated:
        return render(request, 'club/dashboard.html')

    from django.db.models import Q as _Q

    memberships = GroupMembership.objects.filter(
        user=request.user,
        group__disbanded_at__isnull=True,
    ).select_related('group').order_by('-is_favorite', 'group__name')
    my_groups = [m.group for m in memberships]

    my_games = BoardGame.objects.filter(
        owner=request.user,
    ).order_by('name')[:5]

    upcoming_events = Event.objects.filter(
        group__membership__user=request.user,
        group__disbanded_at__isnull=True,
        date__gte=timezone.now(),
    ).select_related('created_by', 'group').order_by('date')[:5]

    return render(request, 'club/dashboard.html', {
        'my_groups': my_groups,
        'my_games': my_games,
        'upcoming_events': upcoming_events,
    })


def public_profile(request, username):
    if not request.user.is_authenticated:
        return redirect('/login/')
    profile_user = get_object_or_404(User, username=username)
    is_own = request.user == profile_user

    context = {
        'profile_user': profile_user,
        'is_own': is_own,
    }

    if is_own or profile_user.show_games:
        context['games'] = BoardGame.objects.filter(
            owner=profile_user,
        ).select_related('owner')

    if is_own or profile_user.show_events:
        attendances = EventAttendance.objects.filter(
            user=profile_user,
        ).select_related('event', 'event__created_by')
        context['attendances'] = attendances

    context['show_date_joined'] = is_own or profile_user.show_date_joined

    return render(request, 'club/profile.html', context)


def user_settings(request):
    if not request.user.is_authenticated:
        return redirect('/login/')

    if request.method == 'POST':
        form = SettingsForm(request.POST, request.FILES)
        if form.is_valid():
            new_email = form.cleaned_data['email']
            new_tz = form.cleaned_data['timezone']
            new_icon = form.cleaned_data.get('verified_icon')
            new_bio = form.cleaned_data.get('bio', '')
            new_picture = form.cleaned_data.get('profile_picture')
            new_show_games = form.cleaned_data.get('show_games', True)
            new_show_events = form.cleaned_data.get('show_events', True)
            new_show_date_joined = form.cleaned_data.get('show_date_joined', True)
            user = request.user

            email_changed = new_email != user.email
            tz_changed = new_tz != user.timezone
            old_icon_id = user.verified_icon_id
            new_icon_id = new_icon.pk if new_icon else None
            icon_changed = old_icon_id != new_icon_id
            bio_changed = new_bio != user.bio
            privacy_changed = (
                new_show_games != user.show_games
                or new_show_events != user.show_events
                or new_show_date_joined != user.show_date_joined
            )

            if email_changed:
                user.email = new_email
                if new_email:
                    user.email_verified = False
                else:
                    user.email_verified = False

            if tz_changed:
                user.timezone = new_tz
                user.timezone_detected = False

            if user.email_verified:
                user.verified_icon = new_icon

            if bio_changed:
                user.bio = new_bio

            if new_picture:
                buffer = resize_profile_picture(new_picture)
                user.profile_picture.save(
                    f'{user.username}_profile.jpg',
                    buffer,
                    save=False,
                )

            user.show_games = new_show_games
            user.show_events = new_show_events
            user.show_date_joined = new_show_date_joined

            if email_changed or tz_changed or icon_changed or bio_changed or new_picture or privacy_changed:
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

            if request.user.is_site_admin:
                offset_hours = request.POST.get('default_voting_offset_hours', '0')
                offset_mins = request.POST.get('default_voting_offset_minutes_field', '0')
                try:
                    total_minutes = int(offset_hours) * 60 + int(offset_mins)
                except (ValueError, TypeError):
                    total_minutes = 0
                site_settings = SiteSettings.load()
                if site_settings.default_voting_offset_minutes != total_minutes:
                    site_settings.default_voting_offset_minutes = total_minutes
                    site_settings.save()

            return redirect('user_settings')
    else:
        form = SettingsForm(initial={
            'email': request.user.email,
            'timezone': request.user.timezone or 'UTC',
            'verified_icon': request.user.verified_icon_id or '',
            'bio': request.user.bio or '',
            'show_games': request.user.show_games,
            'show_events': request.user.show_events,
            'show_date_joined': request.user.show_date_joined,
        })

    site_settings = SiteSettings.load()
    current_total = site_settings.default_voting_offset_minutes
    offset_hours = current_total // 60
    offset_mins = current_total % 60

    return render(request, 'club/settings.html', {
        'form': form,
        'verified_icons': VerifiedIcon.objects.all().order_by('name'),
        'icon_manage_form': VerifiedIconForm(),
        'site_settings': site_settings,
        'offset_hour_choices': list(range(0, 25)),
        'offset_minute_choices': list(range(0, 60, 5)),
        'current_offset_hours': offset_hours,
        'current_offset_minutes': offset_mins,
    })


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
    weight = fetch_bgg_weight(bgg_id)
    if weight is not None:
        data['bgg_weight'] = str(weight)
        data['suggested_complexity'] = weight_to_complexity(weight)
    return JsonResponse(data)


def game_list(request):
    if not request.user.is_authenticated:
        return redirect('/login/')

    games = BoardGame.objects.select_related('owner').all()
    active_tab = request.GET.get('tab', 'all')

    if active_tab == 'my':
        games = games.filter(owner=request.user)

    owner_filter = request.GET.getlist('owner')
    if owner_filter:
        resolved_owners = []
        for o in owner_filter:
            if o == 'myself':
                resolved_owners.append(request.user.username)
            else:
                resolved_owners.append(o)
        if resolved_owners:
            games = games.filter(owner__username__in=resolved_owners)

    players_param = request.GET.get('players', '')
    if players_param:
        try:
            player_count = int(players_param)
            games = games.filter(
                Q(min_players__isnull=False, min_players__lte=player_count)
                & (Q(max_players=0) | Q(max_players__isnull=False, max_players__gte=player_count))
            )
        except (ValueError, TypeError):
            pass

    sort_param = request.GET.get('sort', 'name_asc')
    sort_map = {
        'name_asc': 'name',
        'name_desc': '-name',
        'min_players_asc': 'min_players',
        'min_players_desc': '-min_players',
        'max_players_asc': 'max_players',
        'max_players_desc': '-max_players',
        'owner_asc': 'owner__username',
        'owner_desc': '-owner__username',
    }
    order_by = sort_map.get(sort_param, 'name')
    games = games.order_by(order_by)

    all_owners = User.objects.exclude(pk=request.user.pk).values_list('username', flat=True)

    return render(request, 'club/game_list.html', {
        'games': games,
        'active_tab': active_tab,
        'all_owners': all_owners,
        'current_sort': sort_param,
        'owner_filter': owner_filter,
        'players_filter': players_param,
    })


def game_add(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.method == 'POST':
        form = BoardGameForm(request.POST)
        if form.is_valid():
            game = form.save(commit=False)
            game.owner = request.user
            _process_bgg_link(game, form)
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
    is_superuser_editing_others = (
        request.user.is_superuser and game.owner != request.user
    )
    if game.owner != request.user and not is_superuser_editing_others:
        raise PermissionDenied
    if request.method == 'POST':
        form = BoardGameForm(request.POST, instance=game)
        if form.is_valid():
            _process_bgg_link(game, form)
            form.save()
            if game.complexity:
                Notification.objects.filter(
                    user=request.user,
                    notification_type='missing_complexity',
                    url=f'/games/{game.pk}/edit/',
                    is_read=False,
                ).update(is_read=True)
            if game.max_players is not None:
                Notification.objects.filter(
                    user=request.user,
                    notification_type='missing_max_players',
                    url=f'/games/{game.pk}/edit/',
                    is_read=False,
                ).update(is_read=True)
            return redirect('game_detail', pk=game.pk)
    else:
        form = BoardGameForm(instance=game)
    return render(request, 'club/game_form.html', {
        'form': form,
        'action': 'Edit',
        'is_superuser_editing_others': is_superuser_editing_others,
        'game': game,
    })


def game_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    game = get_object_or_404(BoardGame, pk=pk)
    if game.owner != request.user and not request.user.is_superuser:
        raise PermissionDenied
    if request.method == 'POST':
        game.delete()
        return redirect('game_list')
    return render(request, 'club/game_confirm_delete.html', {
        'game': game,
        'is_superuser_deleting_others': request.user.is_superuser and game.owner != request.user,
    })


def event_list(request):
    if not request.user.is_authenticated:
        groups = Group.objects.filter(discoverable=True, disbanded_at__isnull=True)
    else:
        groups = list(Group.objects.filter(
            Q(discoverable=True) | Q(membership__user=request.user),
            disbanded_at__isnull=True,
        ).distinct())

        if request.user.is_authenticated:
            fav_ids = set(
                GroupMembership.objects.filter(
                    user=request.user, is_favorite=True,
                ).values_list('group_id', flat=True)
            )
            groups.sort(key=lambda g: (0 if g.id in fav_ids else 1, g.name))

    event_groups = []
    for group in groups:
        group_events = Event.objects.filter(
            group=group,
        ).select_related('created_by').order_by('date')
        is_organizer = (
            request.user.is_authenticated
            and is_group_organizer(request.user, group)
        )
        event_groups.append({
            'group': group,
            'events': group_events,
            'is_organizer': is_organizer,
        })

    return render(request, 'club/event_list.html', {
        'event_groups': event_groups,
        'time_midnight': dt_time(0, 0),
    })


def group_event_list(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not can_view_group(request.user, group):
        raise PermissionDenied
    is_organizer = (
        request.user.is_authenticated
        and is_group_organizer(request.user, group)
    )
    events = Event.objects.filter(group=group).select_related('created_by')
    return render(request, 'club/event_list.html', {
        'event_groups': [{'group': group, 'events': events, 'is_organizer': is_organizer}],
        'time_midnight': dt_time(0, 0),
        'group': group,
    })


def group_games(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not can_view_group(request.user, group):
        raise PermissionDenied
    if group.is_disbanded:
        raise PermissionDenied
    games = group.games().select_related('owner').order_by('name')
    return render(request, 'club/group_games.html', {
        'group': group,
        'games': games,
    })


def event_add(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/')
    group = get_object_or_404(Group, slug=slug)
    if not can_create_event(request.user, group):
        raise PermissionDenied
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.date = form.cleaned_data['date']
            event.created_by = request.user
            event.group = group
            offset = form.cleaned_data.get('voting_deadline_offset_minutes') or 0
            event.voting_deadline_offset_minutes = offset
            custom_deadline = form.cleaned_data.get('voting_deadline')
            if custom_deadline:
                event.voting_deadline = custom_deadline
            else:
                event.voting_deadline = event.date - timezone.timedelta(minutes=offset)
            event.save()
            notify_group_event_created(group, event, request.user)
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
    else:
        form = EventForm(initial={
            'voting_deadline_offset_minutes': SiteSettings.load().default_voting_offset_minutes,
        })
    return render(request, 'club/event_form.html', {
        'form': form,
        'action': 'Create',
        'voting_offset': SiteSettings.load().default_voting_offset_minutes,
        'group': group,
    })


def _compute_recurring_dates(start_dt, end_type, occurrence_count, end_date):
    dates = []
    current = start_dt
    if end_type == 'count':
        for _ in range(occurrence_count):
            dates.append(current)
            current = current + timezone.timedelta(days=7)
    else:
        end_dt = timezone.make_aware(
            datetime.combine(end_date, dt_time(23, 59))
        ) if timezone.is_naive(datetime.combine(end_date, dt_time(23, 59))) else datetime.combine(
            end_date, dt_time(23, 59)
        )
        while current <= end_dt:
            dates.append(current)
            current = current + timezone.timedelta(days=7)
    return dates


def event_add_recurring(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/')
    group = get_object_or_404(Group, slug=slug)
    if not can_create_event(request.user, group):
        raise PermissionDenied

    if request.method == 'POST':
        form = RecurringEventForm(request.POST)
        if form.is_valid():
            start_dt = form.cleaned_data['start_datetime']
            end_type = form.cleaned_data['end_type']
            occurrence_count = form.cleaned_data.get('occurrence_count') or 0
            end_date = form.cleaned_data.get('end_date')

            dates = _compute_recurring_dates(start_dt, end_type, occurrence_count, end_date)

            if not dates:
                form.add_error(None, 'No dates could be computed. Check your start date and end condition.')
                return render(request, 'club/event_form_recurring.html', {
                    'form': form,
                    'voting_offset': SiteSettings.load().default_voting_offset_minutes,
                    'group': group,
                })

            date_list = []
            for d in dates:
                date_list.append({
                    'date': d.strftime('%Y-%m-%d'),
                    'time': d.strftime('%H:%M') if d.time() != dt_time(0, 0) else '',
                    'datetime': d.isoformat(),
                    'checked': True,
                })

            vd_date = form.cleaned_data.get('voting_deadline_date')
            vd_time = form.cleaned_data.get('voting_deadline_time')
            vd_offset = form.cleaned_data.get('voting_deadline_offset_minutes') or 0

            form_data = {
                'title': form.cleaned_data['title'],
                'description': form.cleaned_data.get('description', ''),
                'location': form.cleaned_data.get('location', ''),
                'time': form.cleaned_data.get('time').strftime('%H:%M') if form.cleaned_data.get('time') else '',
                'voting_deadline_offset_minutes': vd_offset,
                'voting_deadline_date': vd_date.strftime('%Y-%m-%d') if vd_date else '',
                'voting_deadline_time': vd_time.strftime('%H:%M') if vd_time else '',
            }

            request.session['recurring_event_form_data'] = form_data
            request.session['recurring_event_dates'] = date_list
            return redirect('event_add_recurring_preview', slug=slug)
    else:
        form = RecurringEventForm(initial={
            'voting_deadline_offset_minutes': SiteSettings.load().default_voting_offset_minutes,
        })

    return render(request, 'club/event_form_recurring.html', {
        'form': form,
        'voting_offset': SiteSettings.load().default_voting_offset_minutes,
        'group': group,
    })


def event_add_recurring_preview(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/')
    group = get_object_or_404(Group, slug=slug)
    if not can_create_event(request.user, group):
        raise PermissionDenied

    form_data = request.session.get('recurring_event_dates')
    if not form_data:
        return redirect('event_add_recurring', slug=slug)

    dates_data = request.session.get('recurring_event_dates', [])
    event_data = request.session.get('recurring_event_form_data', {})

    dates = []
    for d in dates_data:
        dt = timezone.datetime.fromisoformat(d['datetime'])
        dates.append({
            'date': d['date'],
            'time': d['time'],
            'datetime': dt,
            'display': dt.strftime('%A, %B %d, %Y') + (f' at {dt.strftime("%I:%M %p")}' if dt.time() != dt_time(0, 0) else ''),
            'checked': d.get('checked', True),
        })

    if request.method == 'POST':
        if 'cancel' in request.POST:
            request.session.pop('recurring_event_form_data', None)
            request.session.pop('recurring_event_dates', None)
            return redirect('group_event_list', slug=slug)

        checked_indices = request.POST.getlist('selected_dates')
        checked_indices = [int(i) for i in checked_indices]

        if not checked_indices:
            return render(request, 'club/event_recurring_preview.html', {
                'dates': dates,
                'event_data': event_data,
                'error': 'You must select at least one date.',
            })

        offset = event_data.get('voting_deadline_offset_minutes', 0) or 0
        time_str = event_data.get('time', '')
        first_event = None

        for idx in checked_indices:
            d = dates_data[idx]
            dt = timezone.datetime.fromisoformat(d['datetime'])

            event = Event(
                title=event_data['title'],
                description=event_data.get('description', ''),
                location=event_data.get('location', ''),
                date=dt,
                created_by=request.user,
                group=group,
                voting_deadline_offset_minutes=offset,
            )
            custom_vd_date = event_data.get('voting_deadline_date')
            custom_vd_time = event_data.get('voting_deadline_time')
            if custom_vd_date:
                vd_t = dt_time(0, 0)
                if custom_vd_time:
                    h, m = custom_vd_time.split(':')
                    vd_t = dt_time(int(h), int(m))
                vd_combined = datetime.combine(
                    datetime.strptime(custom_vd_date, '%Y-%m-%d').date(), vd_t
                )
                vd_combined = timezone.make_aware(vd_combined) if timezone.is_naive(vd_combined) else vd_combined
                event.voting_deadline = vd_combined
            else:
                event.voting_deadline = event.date - timezone.timedelta(minutes=offset)
            event.save()
            first_event = first_event if first_event else event

        if first_event:
            notify_group_event_created(
                group, first_event, request.user, count=len(checked_indices),
            )

        request.session.pop('recurring_event_form_data', None)
        request.session.pop('recurring_event_dates', None)
        return redirect('group_event_list', slug=slug)

    return render(request, 'club/event_recurring_preview.html', {
        'dates': dates,
        'event_data': event_data,
    })


def event_edit(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not is_group_organizer(request.user, event.group):
        raise PermissionDenied

    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            event = form.save(commit=False)
            event.date = form.cleaned_data['date']
            offset = form.cleaned_data.get('voting_deadline_offset_minutes') or 0
            event.voting_deadline_offset_minutes = offset
            custom_deadline = form.cleaned_data.get('voting_deadline')
            if custom_deadline:
                event.voting_deadline = custom_deadline
            else:
                event.voting_deadline = event.date - timezone.timedelta(minutes=offset)
            event.save()
            notify_group_event_updated(event.group, event, request.user)
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
    else:
        form = EventForm(instance=event, initial={
            'voting_deadline_offset_minutes': event.voting_deadline_offset_minutes,
        })
    return render(request, 'club/event_form.html', {
        'form': form,
        'action': 'Edit',
        'voting_offset': event.voting_deadline_offset_minutes,
        'group': event.group,
    })


def event_vote(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not can_view_group(request.user, event.group):
        raise PermissionDenied
    if not EventAttendance.objects.filter(user=request.user, event=event).exists():
        raise PermissionDenied

    event.sync_voting_status()
    event.refresh_from_db()

    games = event.group.games()

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
        return redirect('event_detail', slug=event.group.slug, pk=event.pk)

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


def event_results(request, slug, pk):
    event = get_object_or_404(Event, pk=pk)
    if not is_group_member(request.user, event.group):
        raise PermissionDenied
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


def event_toggle_visibility(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not is_group_admin(request.user, event.group):
        raise PermissionDenied
    event.show_individual_votes = not event.show_individual_votes
    event.save()
    return redirect('event_detail', slug=event.group.slug, pk=event.pk)


def event_toggle_voting(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not is_group_organizer(request.user, event.group):
        raise PermissionDenied
    event.sync_voting_status()
    event.refresh_from_db()

    if event.is_voting_open:
        event.voting_open = False
        event.save()
        notify_group_voting_ended(event.group, event, request.user)
    else:
        if not event.is_active:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        if timezone.now() >= event.voting_deadline:
            return redirect('event_detail', slug=event.group.slug, pk=event.pk)
        event.voting_open = True
        event.save()
        notify_group_voting_resumed(event.group, event, request.user)

    return redirect('event_detail', slug=event.group.slug, pk=event.pk)


def event_detail(request, slug, pk):
    event = get_object_or_404(Event, pk=pk)
    if not can_view_group(request.user, event.group):
        raise PermissionDenied
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
    is_group_organizer_user = (
        request.user.is_authenticated
        and is_group_organizer(request.user, event.group)
    )
    return render(request, 'club/event_detail.html', {
        'event': event,
        'attendees': attendees,
        'is_attending': is_attending,
        'time_midnight': dt_time(0, 0),
        'can_resume': can_resume,
        'is_group_organizer': is_group_organizer_user,
    })


def event_rsvp(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    event = get_object_or_404(Event, pk=pk)
    if not is_group_member(request.user, event.group):
        raise PermissionDenied
    attendance = EventAttendance.objects.filter(
        user=request.user, event=event
    )
    if attendance.exists():
        attendance.delete()
    else:
        EventAttendance.objects.create(user=request.user, event=event)
    return redirect('event_detail', slug=event.group.slug, pk=event.pk)


def _admin_required(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if not (request.user.is_superuser or request.user.is_site_admin):
        raise PermissionDenied
    return None


def add_verified_icon(request):
    redirect_resp = _admin_required(request)
    if redirect_resp:
        return redirect_resp
    if request.method == 'POST':
        form = VerifiedIconForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('user_settings')
        return render(request, 'club/settings.html', {
            'form': SettingsForm(initial={
                'email': request.user.email,
                'timezone': request.user.timezone or 'UTC',
                'verified_icon': request.user.verified_icon_id or '',
            }),
            'verified_icons': VerifiedIcon.objects.all().order_by('name'),
            'icon_manage_form': form,
        })
    return redirect('user_settings')


def delete_verified_icon(request, pk):
    redirect_resp = _admin_required(request)
    if redirect_resp:
        return redirect_resp
    icon = get_object_or_404(VerifiedIcon, pk=pk)
    if request.method == 'POST':
        user_count = User.objects.filter(verified_icon=icon).count()
        if user_count > 0:
            return render(request, 'club/settings.html', {
                'form': SettingsForm(initial={
                    'email': request.user.email,
                    'timezone': request.user.timezone or 'UTC',
                    'verified_icon': request.user.verified_icon_id or '',
                }),
                'verified_icons': VerifiedIcon.objects.all().order_by('name'),
                'icon_delete_error': f'Cannot delete "{icon.name}" — {user_count} user{"s" if user_count != 1 else ""} {"are" if user_count != 1 else "is"} using this icon.',
                'icon_manage_form': VerifiedIconForm(),
            })
        icon.delete()
    return redirect('user_settings')


def notification_list(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    notifications = Notification.objects.filter(user=request.user)
    return render(request, 'club/notification_list.html', {
        'notifications': notifications,
    })


def notification_mark_read(request, pk):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    notif.is_read = True
    notif.save()
    if notif.url:
        return redirect(notif.url)
    return redirect('notification_list')


def notification_mark_all_read(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect('notification_list')


def notification_delete_selected(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.method != 'POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    selected = request.POST.getlist('selected_notifications')
    if selected:
        Notification.objects.filter(
            pk__in=selected,
            user=request.user,
            is_read=True,
        ).delete()
    return redirect('notification_list')


@login_required
def group_list(request):
    from django.db.models import Q
    tab = request.GET.get('tab', 'my')
    query = request.GET.get('q', '')

    memberships = GroupMembership.objects.filter(
        user=request.user,
    ).select_related('group').order_by('-is_favorite', 'group__name')

    my_groups = [m.group for m in memberships]
    member_group_ids = {m.group_id for m in memberships}
    favorite_group_ids = {m.group_id for m in memberships if m.is_favorite}

    if tab == 'my':
        groups = my_groups
    elif tab == 'all':
        groups = list(Group.objects.filter(
            Q(discoverable=True) | Q(membership__user=request.user),
        ).filter(
            disbanded_at__isnull=True,
        ).distinct().order_by('name'))
    elif tab == 'pending':
        groups = []
    else:
        groups = my_groups

    if query:
        from django.utils.text import slugify
        q_lower = query.lower()
        groups = [g for g in groups if q_lower in g.name.lower()]

    pending_requests = GroupJoinRequest.objects.filter(
        user=request.user,
        status='pending',
        expires_at__gt=timezone.now(),
    ).select_related('group') if tab == 'pending' else []

    return render(request, 'club/group_list.html', {
        'groups': groups,
        'tab': tab,
        'query': query,
        'my_groups': my_groups,
        'pending_requests': pending_requests,
        'member_group_ids': member_group_ids,
        'favorite_group_ids': favorite_group_ids,
    })


@login_required
def group_create(request):
    if not can_create_group(request.user):
        from django.contrib import messages
        messages.error(request, 'You have reached your group creation limit. Contact a site admin for more.')
        return redirect('group_list')
    if request.method == 'POST':
        form = GroupCreateForm(request.POST, request.FILES)
        if form.is_valid():
            group = form.save(commit=False)
            group.created_by = request.user
            if group.image:
                buffer = resize_group_image(group.image)
                group.image.save(
                    group.image.name,
                    buffer,
                    save=False,
                )
            group.save()
            GroupMembership.objects.create(
                user=request.user,
                group=group,
                role='admin',
            )
            GroupCreationLog.objects.create(
                user=request.user,
                group=group,
            )
            return redirect('group_dashboard', slug=group.slug)
    else:
        form = GroupCreateForm()
    return render(request, 'club/group_create.html', {'form': form})


def group_dashboard(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not can_view_group(request.user, group):
        raise PermissionDenied

    is_member = group.is_member(request.user) if request.user.is_authenticated else False
    is_admin_user = group.is_admin(request.user) if request.user.is_authenticated else False

    members = GroupMembership.objects.filter(
        group=group,
    ).select_related('user', 'user__verified_icon').order_by('-role', 'joined_at')

    upcoming_events = Event.objects.filter(
        group=group,
        date__gte=timezone.now(),
    ).order_by('date')[:5]

    return render(request, 'club/group_dashboard.html', {
        'group': group,
        'is_member': is_member,
        'is_admin': is_admin_user,
        'members': members,
        'upcoming_events': upcoming_events,
    })


@login_required
def group_settings(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not can_edit_group_settings(request.user, group):
        raise PermissionDenied
    if group.is_disbanded:
        raise PermissionDenied

    if request.method == 'POST':
        form = GroupSettingsForm(request.POST, request.FILES, instance=group, user=request.user)
        if form.is_valid():
            group = form.save(commit=False)
            if 'image' in request.FILES:
                buffer = resize_group_image(request.FILES['image'])
                group.image.save(
                    request.FILES['image'].name,
                    buffer,
                    save=False,
                )
            group.save()
            notify_group_settings_changed(group, request.user)
            return redirect('group_dashboard', slug=group.slug)
    else:
        form = GroupSettingsForm(instance=group, user=request.user)
    return render(request, 'club/group_settings.html', {'form': form, 'group': group})


@login_required
def group_favorite(request, slug):
    group = get_object_or_404(Group, slug=slug)
    membership = get_object_or_404(GroupMembership, user=request.user, group=group)
    if request.method == 'POST':
        membership.is_favorite = not membership.is_favorite
        membership.save(update_fields=['is_favorite'])
    return redirect('group_list')


def group_delete(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/?next=' + request.path)
    if not can_delete_group(request.user):
        raise PermissionDenied

    group = get_object_or_404(Group, slug=slug)

    if request.method == 'POST':
        typed_name = request.POST.get('confirm_name', '')
        if typed_name == group.name:
            group.delete()
            return redirect('group_list')
        return render(request, 'club/group_delete_confirm.html', {
            'group': group,
            'error': 'Group name does not match.',
        })

    return render(request, 'club/group_delete_confirm.html', {'group': group})


def group_restore(request, slug):
    if not request.user.is_authenticated:
        return redirect('/login/?next=' + request.path)
    if not can_restore_group(request.user):
        raise PermissionDenied

    group = get_object_or_404(Group, slug=slug)

    if not group.is_disbanded:
        return redirect('group_dashboard', slug=group.slug)

    if request.method == 'POST':
        group.disbanded_at = None
        group.save(update_fields=['disbanded_at'])
        if not GroupMembership.objects.filter(group=group).exists():
            GroupMembership.objects.create(
                user=request.user,
                group=group,
                role='admin',
            )
        notify_group_restored(group, request.user)
        return redirect('group_dashboard', slug=group.slug)

    return render(request, 'club/group_restore_confirm.html', {'group': group})


def group_members(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not can_view_group(request.user, group):
        raise PermissionDenied

    members = GroupMembership.objects.filter(
        group=group,
    ).select_related('user', 'user__verified_icon').order_by(
        '-role', 'joined_at',
    )

    is_admin_user = group.is_admin(request.user) if request.user.is_authenticated else False

    return render(request, 'club/group_members.html', {
        'group': group,
        'members': members,
        'is_admin': is_admin_user,
    })


@login_required
def group_members_manage(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not is_group_admin(request.user, group):
        raise PermissionDenied

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action = request.POST.get('action')
        membership = GroupMembership.objects.filter(
            user_id=user_id, group=group,
        ).first()

        if membership and membership.user != request.user:
            requires_confirm = (
                membership.role == 'admin'
                and action in ('remove', 'demote_organizer', 'demote_member')
                and not request.POST.get('confirmed')
            )
            if requires_confirm:
                action_labels = {
                    'remove': 'remove',
                    'demote_organizer': 'demote to organizer',
                    'demote_member': 'demote to member',
                }
                return render(request, 'club/group_admin_action_confirm.html', {
                    'group': group,
                    'target_membership': membership,
                    'action': action,
                    'action_label': action_labels[action],
                })
            if action == 'promote_organizer':
                membership.role = 'organizer'
                membership.save(update_fields=['role'])
                notify_group_promoted_organizer(membership.user, group, request.user)
            elif action == 'promote_admin':
                membership.role = 'admin'
                membership.save(update_fields=['role'])
                notify_group_promoted_admin(membership.user, group, request.user)
            elif action == 'demote_member':
                membership.role = 'member'
                membership.save(update_fields=['role'])
                notify_group_demoted_member(membership.user, group, request.user)
            elif action == 'demote_organizer':
                membership.role = 'organizer'
                membership.save(update_fields=['role'])
                notify_group_demoted_organizer(membership.user, group, request.user)
            elif action == 'remove':
                notify_group_removed(membership.user, group, request.user)
                _clean_remove_member(membership.user, group)
                membership.delete()
                if group.membership.count() == 0:
                    group.disbanded_at = timezone.now()
                    group.save(update_fields=['disbanded_at'])
                    notify_group_grace_period(group)

    members = GroupMembership.objects.filter(
        group=group,
    ).select_related('user', 'user__verified_icon').order_by(
        '-role', 'joined_at',
    )

    return render(request, 'club/group_members_manage.html', {
        'group': group,
        'members': members,
    })


@login_required
def group_join(request, slug):
    group = get_object_or_404(Group, slug=slug)

    if group.is_disbanded:
        return render(request, 'club/group_join.html', {
            'group': group,
            'error': 'This group has been disbanded.',
        })

    if group.is_member(request.user):
        return redirect('group_dashboard', slug=group.slug)

    if group.membership.count() >= group.max_members:
        return render(request, 'club/group_join.html', {
            'group': group,
            'error': 'This group is full.',
        })

    if request.method == 'POST':
        if group.join_policy == 'open':
            GroupMembership.objects.create(
                user=request.user,
                group=group,
                role='member',
            )
            notify_group_member_joined(group, request.user, method='open join')
            return redirect('group_dashboard', slug=group.slug)
        elif group.join_policy == 'request':
            if not GroupJoinRequest.objects.filter(
                user=request.user, group=group, status='pending',
            ).exists():
                GroupJoinRequest.objects.create(
                    user=request.user,
                    group=group,
                    expires_at=timezone.now() + __import__('datetime').timedelta(days=7),
                )
                notify_group_join_request(group, request.user)
            return render(request, 'club/group_join.html', {
                'group': group,
                'message': 'Your join request has been submitted.',
            })
        else:
            raise PermissionDenied

    return render(request, 'club/group_join.html', {'group': group})


@login_required
def group_leave(request, slug):
    group = get_object_or_404(Group, slug=slug)
    membership = get_object_or_404(
        GroupMembership, user=request.user, group=group,
    )

    if membership.role == 'admin':
        other_admins = GroupMembership.objects.filter(
            group=group, role='admin',
        ).exclude(user=request.user).exists()

        if not other_admins:
            other_members = GroupMembership.objects.filter(
                group=group,
            ).exclude(user=request.user)
            if other_members.exists():
                if request.method == 'POST':
                    form = SuccessorPickForm(
                        request.POST, members=other_members,
                    )
                    if form.is_valid():
                        successor_id = form.cleaned_data['successor']
                        GroupMembership.objects.filter(
                            user_id=successor_id, group=group,
                        ).update(role='admin')
                        notify_group_member_left(group, request.user)
                        _clean_remove_member(request.user, group)
                        membership.delete()
                        return redirect('group_list')
                else:
                    form = SuccessorPickForm(members=other_members)
                return render(request, 'club/group_leave_confirm.html', {
                    'group': group,
                    'form': form,
                    'members': other_members,
                    'needs_successor': True,
                })

    if request.method == 'POST':
        notify_group_member_left(group, request.user)
        _clean_remove_member(request.user, group)
        membership.delete()
        if group.membership.count() == 0:
            group.disbanded_at = timezone.now()
            group.save(update_fields=['disbanded_at'])
            notify_group_grace_period(group)
        return redirect('group_list')

    remaining = GroupMembership.objects.filter(group=group).count()
    return render(request, 'club/group_leave_confirm.html', {
        'group': group,
        'needs_successor': False,
        'is_last_member': remaining == 1,
    })


@login_required
def group_join_request_manage(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not is_group_admin(request.user, group):
        raise PermissionDenied

    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        join_request = GroupJoinRequest.objects.filter(
            pk=request_id, group=group, status='pending',
        ).first()

        if join_request:
            try:
                if action == 'approve':
                    join_request.approve()
                    notify_group_join_approved(join_request.user, group, request.user)
                    notify_group_member_joined(group, join_request.user, method='join request')
                elif action == 'reject':
                    join_request.reject()
                    notify_group_join_rejected(join_request.user, group, request.user)
            except ValueError:
                pass

    requests = GroupJoinRequest.objects.filter(
        group=group, status='pending', expires_at__gt=timezone.now(),
    ).select_related('user').order_by('-created_at')

    return render(request, 'club/group_join_request_manage.html', {
        'group': group,
        'requests': requests,
    })


def _clean_remove_member(user, group):
    from .models import EventAttendance
    upcoming_events = Event.objects.filter(
        group=group,
        date__gte=timezone.now(),
    )
    EventAttendance.objects.filter(
        user=user,
        event__in=upcoming_events,
    ).delete()
    Vote.objects.filter(
        user=user,
        event__in=upcoming_events,
    ).delete()


@login_required
def group_invite_create(request, slug):
    group = get_object_or_404(Group, slug=slug)
    if not is_group_admin(request.user, group):
        raise PermissionDenied

    if group.is_disbanded:
        raise PermissionDenied

    invite = None
    if request.method == 'POST':
        invite = GroupInvite.objects.create(
            group=group,
            created_by=request.user,
            expires_at=timezone.now() + __import__('datetime').timedelta(days=7),
        )
        notify_group_invite_created(group, request.user)

    return render(request, 'club/group_invite.html', {
        'group': group,
        'invite': invite,
    })


def group_invite_accept(request, token):
    invite = GroupInvite.objects.filter(token=token).first()

    if not invite:
        return render(request, 'club/group_invite_accept.html', {
            'error': 'This invite link is invalid.',
        })

    if invite.used:
        return render(request, 'club/group_invite_accept.html', {
            'error': 'This invite has already been used.',
        })

    if not invite.is_valid():
        return render(request, 'club/group_invite_accept.html', {
            'error': 'This invite has expired.',
        })

    if invite.group.is_disbanded:
        return render(request, 'club/group_invite_accept.html', {
            'error': 'This group has been disbanded.',
        })

    if not request.user.is_authenticated:
        return redirect(f'/login/?next=/invite/{token}/')

    try:
        invite.use(request.user)
        notify_group_member_joined(invite.group, request.user, method='invite')
        return redirect('group_dashboard', slug=invite.group.slug)
    except ValueError as e:
        return render(request, 'club/group_invite_accept.html', {
            'error': str(e),
        })
