from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ActivityFeedItem, User, BoardGame, Event, EventAttendance, EventTag, GameTag, Notification, TagRequest, VerifiedIcon, Vote


admin.site.register(User, UserAdmin)


@admin.register(VerifiedIcon)
class VerifiedIconAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(BoardGame)
class BoardGameAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'group', 'complexity', 'bgg_weight', 'min_players', 'max_players', 'created_at')
    list_filter = ('owner', 'group', 'complexity')
    search_fields = ('name',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'location', 'created_by', 'is_active', 'duration_minutes')
    list_filter = ('is_active', 'show_individual_votes')
    search_fields = ('title',)


@admin.register(EventAttendance)
class EventAttendanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'joined_at')
    list_filter = ('event',)


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ('user', 'event', 'board_game', 'rank')
    list_filter = ('event',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'message', 'is_read', 'notification_type', 'created_at')
    list_filter = ('is_read', 'notification_type')
    search_fields = ('user__username', 'message')


@admin.register(GameTag)
class GameTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_at')
    search_fields = ('name',)


@admin.register(EventTag)
class EventTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_at')
    search_fields = ('name',)


@admin.register(TagRequest)
class TagRequestAdmin(admin.ModelAdmin):
    list_display = ('name', 'tag_type', 'status', 'requested_by', 'created_at', 'reviewed_by')
    list_filter = ('status', 'tag_type')
    search_fields = ('name', 'requested_by__username')


@admin.register(ActivityFeedItem)
class ActivityFeedItemAdmin(admin.ModelAdmin):
    list_display = ('activity_type', 'actor', 'event', 'group', 'timestamp')
    list_filter = ('activity_type',)
    search_fields = ('actor__username', 'event__title', 'group__name')
