from django.contrib import admin
from django.http import HttpRequest
from typing import TYPE_CHECKING
from .models import Settings, Chunk


class ChunkInline(admin.StackedInline[Chunk, Settings] if TYPE_CHECKING else admin.StackedInline):
    model: type[Chunk] = Chunk
    fields = ('content',)
    max_num = 0        # don't allow adds
    can_delete = False

class SettingsAdmin(admin.ModelAdmin[Settings] if TYPE_CHECKING else admin.ModelAdmin):

    fieldsets = (
            ('Registration', {
                'fields': (
                    ( 'email_validation_regex',
                      'mat_number_validation_regex'),
                    'deny_registration_from',
                    'acount_activation_days',
                    ( 'account_manual_validation',
                      'requires_disclaimer_acceptance',
                      'new_users_via_sso' )
                )
            }),
            ('Solutions and Attestations', {
                'fields': (
                    'accept_all_solutions',
                    'deadline_tolerance',
                    'tutors_can_edit_solutions',
                    'anonymous_attestation',
                    'attestation_allow_run_checkers',
                    ('final_grades_arithmetic_option',
                     'final_grades_plagiarism_option')
                )
            }),
            ('Attestation Publishing/Viewing', {
                 'fields': (
                     'invisible_attestor',
                     'attestation_reply_to',
                 )
            })
        )
    inlines = [ChunkInline]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

admin.site.register(Settings, SettingsAdmin)
