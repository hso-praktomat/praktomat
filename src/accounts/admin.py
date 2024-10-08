from random import randint
from django.utils.translation import gettext_lazy
from django.contrib import admin, messages
from django.contrib.auth.models import User as UserBase, Group
from django.contrib.auth.admin import UserAdmin as UserBaseAdmin, GroupAdmin as GroupBaseAdmin
from django.db.models import Count
from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from accounts.models import User, Tutorial
from accounts.forms import AdminUserCreationForm, AdminUserChangeForm

import accounts.views

from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse


class UserAdmin(UserBaseAdmin):
    model = User

    # add active status
    list_display = ('username', 'first_name', 'last_name', 'mat_number', 'tutorial', 'is_active', 'accepted_disclaimer', 'is_trainer', 'is_tutor', 'is_coordinator', 'email', 'date_joined', 'is_failed_attempt', 'programme' )
    list_filter = ('groups', 'tutorial', 'is_staff', 'is_superuser', 'is_active', 'programme')
    search_fields = ['username', 'first_name', 'last_name', 'mat_number', 'email']
    date_hierarchy = 'date_joined'
    actions = ['set_active', 'set_inactive', 'set_tutor', 'distribute_to_tutorials', 'export_users']
    readonly_fields = ('last_login', 'date_joined', 'useful_links',)
    # exclude user_permissions
    fieldsets = (
            (None, {'fields': ('username', 'password', 'useful_links')}),
            (gettext_lazy('Personal info'), {'fields': ('first_name', 'last_name', 'email', 'mat_number', 'programme')}),
            (gettext_lazy('Permissions'), {'fields': ('is_active', 'accepted_disclaimer', 'is_staff', 'is_superuser',)}),
            (gettext_lazy('Groups'), {'fields': ('groups', 'tutorial')}),
            (gettext_lazy('Important dates'), {'fields': ('last_login', 'date_joined')}),
            (gettext_lazy('Custom text'), {'fields': ('user_text',)}),
        )

    form = AdminUserChangeForm
    add_form = AdminUserCreationForm

    def is_trainer(self, user):
        return user.is_trainer
    is_trainer.boolean = True

    def is_tutor(self, user):
        return user.is_tutor
    is_tutor.boolean = True

    def is_coordinator(self, user):
        return user.is_coordinator
    is_coordinator.boolean = True

    def is_failed_attempt(self, user):
        successfull = [ u for u in User.objects.all().filter(mat_number=user.mat_number) if u.is_active]
        return (not successfull)
    is_failed_attempt.boolean = True

    def set_active(self, request, queryset):
        """ Set active action """
        queryset.update(is_active=True)
        self.message_user(request, "Users were successfully activated.")

    def set_inactive(self, request, queryset):
        """ Set inactive action """
        queryset.update(is_active=False)
        self.message_user(request, "Users were successfully inactivated.")

    @atomic
    def set_tutor(self, request, queryset):
        """ Change students to tutors """
        tutor_group = Group.objects.get(name='Tutor')
        user_group = Group.objects.get(name='User')
        for user in queryset:
            user.groups.add(tutor_group)
            user.groups.remove(user_group)
            user.save()
        self.message_user(request, "Users were successfully made to tutors.")

    @atomic
    def distribute_to_tutorials(self, request, queryset):
        """ Distribute selected users evenly to all tutorials """
        users = list(queryset)
        for user in users:
            # remove tutorial from users so we can find the tutorial with the least amount of users
            user.tutorial = None
            user.save()
        while(users):
            # get random user and put him in the least populated tutorial
            user = users.pop(randint(0, len(users)-1))
            tutorial = Tutorial.objects.annotate(Count('user')).order_by('user__count')[0]
            user.tutorial = tutorial
            user.save()
        self.message_user(request, "All users were successfully distributed.")

    def export_users(self, request, queryset):
        from django.http import HttpResponse
        data = User.export_user(queryset)
        response = HttpResponse(data, content_type="application/xml")
        response['Content-Disposition'] = 'attachment; filename=user_export.xml'
        return response

    def get_urls(self):
        """ Add URL to user import """
        urls = super(UserAdmin, self).get_urls()
        from django.urls import re_path
        my_urls = [re_path(r'^import/$', accounts.views.import_user, name='user_import')]
        my_urls += [re_path(r'^import_ldap/$', accounts.views.import_ldap_user, name='ldap_user_import')] 
        my_urls += [re_path(r'^import_tutorial_assignment/$', accounts.views.import_tutorial_assignment, name='import_tutorial_assignment')]
        my_urls += [re_path(r'^import_user_texts/$', accounts.views.import_user_texts, name='import_user_texts')]
        return my_urls + urls

    def useful_links(self, instance):
        if instance.pk:
            return format_html (
                '<a href="{1}">Solutions by {0}</a> • <a href="{2}">Attestations for {0}</a> • <a href="{3}">Attestations by {0}</a>',
                instance,
                reverse('admin:solutions_solution_changelist') + ("?author__user_ptr__exact=%d" % instance.pk),
                reverse('admin:attestation_attestation_changelist') + ("?solution__author__user_ptr__exact=%d" % instance.pk),
                reverse('admin:attestation_attestation_changelist') + ("?author__exact=%d" % instance.pk),
                )
        else:
            return ""

    def save_model(self, request, obj, form, change):
        """ give a user both superuser and staff rights if he obtains the trainer role """
        if change:
            was_trainer = get_object_or_404(User, pk=obj.id).is_trainer
            is_trainer = "Trainer" in [g.name for g in form.cleaned_data['groups']]
            if is_trainer and not was_trainer and not (obj.is_staff and obj.is_superuser):
                obj.is_superuser = True
                obj.is_staff = True
                messages.warning(request, 'The user "%s" was automatically made staff member and superuser (because he was made a trainer)' % obj)
            obj.save()
        else:
            # need to save object to set many2many relationship
            obj.save()
            obj.groups.set(Group.objects.filter(name='User'))
            obj.save()


# This should work in Django 1.4 :O
# from django.contrib.admin import SimpleListFilter
# class FailedRegistrationAttempts(admin.SimpleListFilter):
#    title = gettext_lazy('Registration')
#
#    def lookups(self,request,model_admin):
#        return ( (('failed'), gettext_lazy('failed')), (('successfull'), gettext_lazy('sucessfull')) )
#
#    def queryset(self,request,users):
#        failed = User.objects.all().values('mat_number').annotate(failed=Count('mat_number')).filter(failed__gt=1)
#        if self.value() == 'failed':
#            return users.filter(mat_number__in=[u['mat_number'] for u in  failed])
#
#        if self.value() == 'successfull':
#            return user.exclude(mat_number__in=[u['mat_number'] for u in  failed])


admin.site.unregister(UserBase)
admin.site.register(User, UserAdmin)

class GroupAdmin(GroupBaseAdmin):
    def get_urls(self):
        """ Add URL to user import """
        urls = super(GroupAdmin, self).get_urls()
        from django.urls import re_path
        my_urls = [re_path(r'^(\d+)/import_matriculation_list/$', accounts.views.import_matriculation_list, name='import_matriculation_list')]
        return my_urls + urls

admin.site.unregister(Group)
admin.site.register(Group, GroupAdmin)

class TutorialAdmin(admin.ModelAdmin):
    model = Tutorial
    list_display = ('name', 'view_url', 'tutors_flat',)

    class Media:
        css = {
            "all": ("styles/admin_style.css",)
        }

    def view_url(self, tutorial):
        return mark_safe('<a href="%s">View</a>' % (reverse('tutorial_overview', args=[tutorial.id])))
    view_url.short_description = 'View (Tutor Site)'

admin.site.register(Tutorial, TutorialAdmin)
