import os, shutil
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.management.commands.compilemessages import has_bom
from django.core.management.commands.makemessages import make_messages, handle_extensions
from django.http import Http404
from django.http import HttpResponseRedirect
from django.utils.encoding import force_unicode
from django.utils.importlib import import_module
from django.utils.text import capfirst
from django.utils.translation import to_locale, ugettext as _
from django.views.generic import TemplateView, FormView
from forms import PoFileForm
from models import Language
from utils import compile_message_file, concat_message_files, reset_translations

class GenerateTranslationMessagesView(TemplateView):
    template_name ='admin/includes/translation_messages_list.html'

    def get(self, request, *args, **kwargs):
        
        if not request.is_ajax():
            raise Http404
        
        if not request.user.has_perm('translations.edit_translations'):
            raise PermissionDenied

        try:
            self.language = Language.objects.get(name=args[0])
            self.locale = to_locale(self.language.name)
        except Language.DoesNotExist:
            raise Http404
        
        if settings.LOCALE_PATHS:
            #check if the folder for this language exists and attempt to create it if id does not exist
            self.po_path = os.path.join(settings.LOCALE_PATHS[0], self.locale, 'LC_MESSAGES')
            if not os.path.exists(self.po_path):
                try:
                    os.makedirs(self.po_path)
                except:
                    self.error = _('Could not create the target folder.')
        else:
            self.error = _('<b>Configuration error!</b> Please set the LOCALE_PATHS project setting to allow the creation of a unified messages catalog.')
        
        #delete files if requested
        if request.GET.get('delete', 0):
            for file_ in os.listdir(self.po_path):
                if file_.endswith('.po') or file_.endswith('.mo'):
                    os.unlink(os.path.join(self.po_path, file_))
        
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)
    
    def get_context_data(self, **kwargs):
        context = super(GenerateTranslationMessagesView, self).get_context_data(**kwargs)
        
        if hasattr(self, 'error') and self.error:
            context['error'] = self.error
            return context
        
        #locate the current directory
        curr_dir = os.curdir
        domain_dict = {'django' : ['html','txt'], 'djangojs' : ['js']}
        was_empty = True
        
        lang_files = []
        #iterate over the installed applications and copy their po files
        #for this language to the appropriate folder 
        for app_name in settings.INSTALLED_APPS:    
            
            mod = import_module(app_name)
            mod_root = os.path.dirname(mod.__file__)

            original_path = os.path.join(mod_root, 'locale', to_locale(self.language.name), 'LC_MESSAGES')
            if os.path.exists(original_path):
                
                if not app_name.startswith('django.contrib'):
                    #move original files to a temp file
                    #and copy the project-wise files to the appropriate directory 
                    for file_ in list(os.listdir(original_path)):
                        if file_.endswith('.po'):
                            application_file = os.path.join(original_path, file_)
                            yawdtrans_file = os.path.join(self.po_path, '%s-%s' % (app_name, file_))
                            
                            #backup original file
                            shutil.copy2(application_file, 
                                os.path.join(original_path, 'original-%s' % file_))
                            
                            #replace original file with the yawd version
                            #so that it gets updated
                            if os.path.exists(yawdtrans_file):
                                was_empty = False
                                shutil.copy2(yawdtrans_file, application_file)

                    #makemessages excluding the core applications
                    os.chdir(mod_root)
                    for key, value in domain_dict.items():
                        make_messages(locale=self.locale, domain=key, extensions=handle_extensions(value), verbosity=0)
                    os.chdir(curr_dir)

                #iterate over the availale po files
                for file_ in list(os.listdir(original_path)):
                    if not file_.startswith('original-') and file_.endswith('.po'):

                        original_file_path = os.path.join(original_path, file_)
                        file_name = '%s-%s' % (app_name, file_)
                        
                        #copy file 
                        shutil.copy2(original_file_path, os.path.join(self.po_path, file_name))
                        
                        #unlink updated file
                        if not app_name.startswith('django.contrib'):
                            os.unlink(original_file_path)
                        
                        lang_files.append(file_name)
                
                if not app_name.startswith('django.contrib'):
                    for file_ in os.listdir(original_path):
                        #put back the original application files
                        if file_.startswith('original-') and file_.endswith('.po'):
                            shutil.move(os.path.join(original_path, file_), os.path.join(original_path, file_.replace('original-','')))
        
        #concat all messages in a single .po file for each domain
        for domain in domain_dict:
            file_name = '%s.po' % domain
            uni_django_path = os.path.join(self.po_path, file_name)
            
            if os.path.exists(uni_django_path):
                os.unlink(uni_django_path)
            
            source_files = []
            for file_ in lang_files:
                if file_.endswith(file_name):
                    source_files.append(os.path.join(self.po_path, file_))
            
            #merge .po files
            concat_message_files(source_files, uni_django_path)
            #compile django.po
            if not has_bom(uni_django_path):
                compile_message_file(uni_django_path)

        #reset the cached translation messages so that
        #we do not need to restart the web server
        reset_translations(self.language.name, was_empty)
        
        context['lang_files'] = sorted(lang_files)
        return context
    

class TranslationMessagesView(TemplateView):
    template_name = 'admin/translation_messages.html'
    
    def get(self, request, *args, **kwargs):

        if not request.user.has_perm('translations.view_translations'):
            raise PermissionDenied
        
        try:
            self.language = Language.objects.get(name=args[0])
            self.locale = to_locale(self.language.name)
        except Language.DoesNotExist:
            raise Http404

        context = self.get_context_data(**kwargs)
        return self.render_to_response(context) 
    
    def get_context_data(self, **kwargs):
        context = super(TranslationMessagesView, self).get_context_data(**kwargs)
        
        opts = self.language._meta
        
        context['title'] = _('Translate Static Messages')
        context['language'] = self.language
        context['app_label'] = opts.app_label
        context['module_name'] = capfirst(force_unicode(opts.verbose_name_plural))
        
        if not settings.LOCALE_PATHS:
            context['error'] = _('<b>Configuration error!</b> Please set the LOCALE_PATHS project setting to allow the creation of a unified messages catalog.')
            return context
        
        context['lang_files'] = []
        po_path = os.path.join(settings.LOCALE_PATHS[0], self.locale, 'LC_MESSAGES')
        if os.path.exists(po_path):
            for file_ in os.listdir(po_path):
                if file_.endswith('.po') and not file_ in ['django.po', 'djangojs.po']:
                    context['lang_files'].append(file_)
            context['lang_files'].sort()
        
        if not os.path.exists(po_path) or not context['lang_files']:
            context['warning'] = _('The system does not appear to have any translation messages for this language. Please use the "Generate messages" button.')

        return context

class TranslationMessagesEditView(FormView):
    template_name = 'admin/edit_translation_messages.html'
    form_class = PoFileForm
    success_url = '../'
    
    def dispatch(self, request, *args, **kwargs):
        """
        Overidden dispatch method to check if user has the right to edit
        the .po file.
        """
        
        if not request.user.has_perm('translations.edit_translations'):
            raise PermissionDenied
        
        return super(TranslationMessagesEditView, self).dispatch(request, *args, **kwargs)
    
    def get_initial(self):
        """
        Attempt to load the po file and put its contents in the form's
        initial data
        """

        try:
            self.language = Language.objects.get(name=self.args[0])
        except Language.DoesNotExist:
            raise Http404
        
        if settings.LOCALE_PATHS:
            #check if the folder for this language exists and attempt to create it if id does not exist
            self.po_path = os.path.join(settings.LOCALE_PATHS[0], to_locale(self.language.name), 'LC_MESSAGES')
        else:
            raise Http404
        
        self.po_file = self.args[1]
        
        try:
            file_ = open(os.path.join(self.po_path, self.po_file), 'r')
            contents = file_.read()
            file_.close()
            
            return { 'po_content' : contents }
        except:
            raise Http404
        
    def get_context_data(self, **kwargs):
        context = super(TranslationMessagesEditView, self).get_context_data(**kwargs)
        
        opts = self.language._meta
        
        context['title'] = u'%s %s' % (_('Edit'), self.po_file)
        context['language'] = self.language
        context['app_label'] = opts.app_label
        context['module_name'] = capfirst(force_unicode(opts.verbose_name_plural))
        
        #these context variable are used bu the 'submit_row' admin tag
        context['has_delete_permission'] = False
        context['has_add_permission'] = False
        context['has_change_permission'] = True
        context['change'] = True
        context['is_popup'] = False
        context['save_as']= False
        context['opts'] = opts
        
        return context

    def form_valid(self, form):
        try:
            file_path = os.path.join(self.po_path, self.po_file)
            
            file_ = open(file_path, 'w+')
            file_.write(form.cleaned_data['po_content'])
            file_.close()
            
            domain = 'django.po' if self.po_file.endswith('django.po') else 'djangojs.po'
            uni_django_path = os.path.join(self.po_path, domain)
            source_files = []
            
            #iterate over the installed applications, locate & concat 
            #the corresponding global django.po or djangojs.po file
            for app_name in settings.INSTALLED_APPS:
                local_django = os.path.join(self.po_path, '%s-%s' % (app_name, domain))
                if os.path.exists(local_django):
                    source_files.append(local_django)

            concat_message_files(source_files, uni_django_path)
            
            if not has_bom(uni_django_path):
                compile_message_file(uni_django_path)

                
            #reset the cached translation messages so that
            #we do not need to restart the web server
            reset_translations(self.language.name)
            
            messages.add_message(self.request, messages.SUCCESS, _(('The file %(file)s was succesfuly updated.' % { 'file' : self.po_file })))
        except:
            messages.add_message(self.request, messages.ERROR, _(('The file %(file)s could not be saved.' % { 'file' : self.po_file })))
        
        #save and continue editing
        if "_continue" in self.request.POST:
            return HttpResponseRedirect('../%s' % self.po_file)

        return super(TranslationMessagesEditView, self).form_valid(form)
        