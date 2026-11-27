/** @odoo-module **/

import {_t} from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

export class IbanWidget extends CharField {
    _onDragEnter(ev) {
        ev.stopPropagation();
        ev.preventDefault();
    }
    _onDragOver(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        ev.currentTarget.classList.remove('dnd_out');
        ev.currentTarget.classList.add('dnd_inside');
    }
    _onDrop(ev) {
        ev.preventDefault();
        this.handleFileUpload(ev.dataTransfer.files);
    }

    _onClickWrapper(ev) {
        document.querySelectorAll('.files').forEach(fileInput => {
            fileInput.value = "";
            fileInput.click();
        });
    }

    _uploadFile(ev) {
        if (ev.currentTarget.files.length > 0) {
            this.handleFileUpload(ev.currentTarget.files);
        }
    }

    _onButtonSave(e) {
        e.preventDefault();
        document.querySelectorAll('.alert-warning.dnd-alert').forEach(alert => alert.remove());
        if (Object.keys(this.files).length <= 0) {
            this.notification.add(_t("There is no files selected"), {
                type: "danger"
            });
        } else if (Object.keys(this.files).length > 1 && this.env.model.root.context.active_ids) {
            this.notification.add(_t("There is no files selected"), {
                type: "danger"
            });
        } else {
            document.getElementById('dragandrophandler').style.display = 'none';
            document.getElementById('dndfooter').querySelector("#save").disabled = true;
            document.getElementById('filescontent').querySelectorAll(".xml_cont").forEach(element => {
                element.classList.remove('xml_cont_hover');
            });
            this.readFiles(this.files);
        }
    }

    _onButtonClose(e) {
        e.preventDefault();
        const attachWidgetElement = document.getElementById("attach_widget");
        if (attachWidgetElement && attachWidgetElement.parentElement) {
            attachWidgetElement.parentElement.classList.add("o_field_widget");
        }
        return this.action.doAction({
            type: "ir.actions.act_window_close"
        });
    }

    async _onButtonShow(e) {
        e.preventDefault();
        if (this.attachment_ids.length > 0) {
            var domain = [
                ['id', 'in', this.attachment_ids]
            ];
            this.action.doAction({
                name: _t('XML Attchments'),
                view_type: 'list',
                view_mode: 'list,form',
                res_model: 'ir.attachment',
                type: 'ir.actions.act_window',
                views: [
                    [false, 'list'],
                    [false, 'form']
                ],
                target: 'current',
                domain: domain,
            });
        }
    }

    setup() {
        super.setup();
        this.actionService = useService("action");
        this.files = {};
        this.uploading_files = false;
        this.attachment_ids = [];
        this.notification = useService("notification");
        this.action = useService("action");
        var handler = document.getElementById("dragandrophandler");

        document.addEventListener('dragenter', function(e) {
            e.stopPropagation();
            e.preventDefault();
            var handler = document.getElementById("dragandrophandler");
            if (handler) {
                handler.classList.remove('dnd_inside', 'dnd_normal');
                handler.classList.add('dnd_out');
            }
        });

        document.addEventListener('dragover', function(e) {
            e.stopPropagation();
            e.preventDefault();
        });

        document.addEventListener('drop', function(e) {
            e.stopPropagation();
            e.preventDefault();
            var handler = document.getElementById("dragandrophandler");
            if (handler) {
                handler.classList.remove('dnd_out', 'dnd_inside');
                handler.classList.add('dnd_normal');
            }
        });

        document.addEventListener('dragleave', function(e) {
            e.stopPropagation();
            e.preventDefault();
            var handler = document.getElementById("dragandrophandler");
            if (handler && !e.clientX && !e.clientY) {
                handler.classList.remove('dnd_out', 'dnd_inside');
                handler.classList.add('dnd_normal');
            }
        });
    }

    remove_all_xml(e) {
        const alertnode = e.currentTarget.parentElement.parentElement;
        const filekey_current = alertnode.getAttribute('tag');
        const self = this;
        let remove_current_file = false;
        const files = this.files;

        const wrong_files = Object.values(files).filter(file => file.iscorrect === false);
        const readfiles = {};

        wrong_files.forEach(file => {
            if (!file.iscorrect) {
                const fr = new FileReader();
                fr.onload = function() {
                    if (!file.iscorrect) {
                        readfiles[file.name] = fr.result;
                    }

                    if (Object.keys(wrong_files).length === Object.keys(readfiles).length) {
                        rpc("/web/dataset/call_kw/multi.file.attach.xmls.wizard/remove_wrong_file", {
                            model: 'multi.file.attach.xmls.wizard',
                            method: 'remove_wrong_file',
                            args: [readfiles],
                            kwargs: {
                                context: self.env.model.root.context,
                            },
                        }).then(function(results) {
                            results.forEach(filekey => {
                                self.removeWrongAlerts(alertnode, filekey, true);
                            });
                        });
                    }
                };
                fr.readAsDataURL(file);
            }
        });

        Object.keys(self.alerts_in_queue.alertHTML).forEach(filekey => {
            const file = self.alerts_in_queue.alertHTML[filekey];
            if (file.alert && file.alert[0] && file.alert[0].innerText.includes('The XML UUID</span> belong to other move')) {
                if (filekey_current === filekey) {
                    remove_current_file = true;
                } else {
                    delete self.alerts_in_queue.alertHTML[filekey];
                    delete self.files[filekey];
                }
            } else if (file.alert && file.alert[0] && file.alert[0].innerText.includes('The move reference</span> belong to other')) {
                if (filekey_current === filekey) {
                    remove_current_file = true;
                } else {
                    delete self.alerts_in_queue.alertHTML[filekey];
                    delete self.files[filekey];
                }
            }
        });

        if (remove_current_file) {
            this.removeWrongAlerts(alertnode, filekey_current, true);
        }
    }

    remove_single_xml(e) {
        const filekey = e.currentTarget.getAttribute('title');
        delete this.files[filekey];

        const element = e.currentTarget;
        element.style.transition = 'opacity 0.5s';
        element.style.opacity = '0';
        setTimeout(() => element.remove(), 500);
    }

    remove_xml(e) {
        var type = e.currentTarget.getAttribute('tag');
        var alertnode = e.currentTarget.parentElement.parentElement;
        var filekey = alertnode.getAttribute('tag');
        var self = this;
        if (type === 'remove') {
            this.removeWrongAlerts(alertnode, filekey, true);
        } else if (type === 'partner') {
            rpc("/web/dataset/call_kw/multi.file.attach.xmls.wizard/create_partner", {
                model: 'multi.file.attach.xmls.wizard',
                method: 'create_partner',
                args: [this.alerts_in_queue.alertHTML[filekey].xml64, filekey],
                kwargs: {
                    context: self.env.model.root.context,
                },
            }).then(function() {
                self.sendErrorToServer(self.alerts_in_queue.alertHTML[filekey].xml64, filekey, 'check_xml');
            });
        } else if (type === 'tryagain') {
            this.sendErrorToServer(this.alerts_in_queue.alertHTML[filekey].xml64, filekey, 'check_xml');
        } else if (type === 'forcesave') {
            self.env.model.root.context = Object.assign(self.env.model.root.context, {
                'force_save': true
            });
            self.sendErrorToServer(self.alerts_in_queue.alertHTML[filekey].xml64, filekey, 'check_xml');
        }
    }

    handleFileUpload(files) {
        var self = this;
        if (self.uploading_files) {
            self.notification.add(_t("There are files uploading"), {
                title: _t('Error'),
                type: "danger"
            });
        } else {
            self.uploading_files = true;
            var files_used = [];
            var wrong_files = [];
            Array.from(files).forEach(function(file) {
                if (file.type !== 'text/xml') {
                    wrong_files.push(file.name);
                } else if (Object.prototype.hasOwnProperty.call(self.files, file.name)) {
                    files_used.push(file.name);
                } else {
                    self.files[file.name] = file;
                    var newelement = document.createElement('div');
                    newelement.className = 'xml_cont xml_cont_hover';
                    newelement.id = 'xml_cont_hover';
                    newelement.title = file.name;
                    newelement.style.opacity = '0';
                    newelement.innerHTML = '<img class="xml_img" height="100%" align="left" hspace="5"/>' +
                        '<p>' + file.name + '</p><div class="remove_xml" >&times;</div>';
                    document.getElementById('filescontent').appendChild(newelement);
                    setTimeout(() => {
                        newelement.style.opacity = '1';
                    }, 0);
                }
            });

            var alert_message = '';
            if (wrong_files.length > 0) {
                alert_message += _t('<strong>Info!</strong> You only can upload XML files.<br>') +
                    wrong_files.join(" <b style='font-size:15px;font-wight:900;'>&#8226;</b> ");
            }
            if (files_used.length > 0) {
                if (alert_message !== '') {
                    alert_message += '<br>';
                }
                alert_message += _t('<strong>Info!</strong> Some files are already loaded.<br>') +
                    files_used.join(" <b style='font-size:15px;font-wight:900;'>&#8226;</b> ");
            }
            if (alert_message !== '') {
                document.getElementById('alertscontent').innerHTML = '<div class="alert alert-warning dnd-alert">' +
                    '<a href="#" class="close" data-dismiss="alert" aria-label="close">&times;</a>' + alert_message +
                    '</div>';
            }
            self.uploading_files = false;
        }
        document.getElementById("xml_cont_hover").addEventListener('click', self.remove_single_xml.bind(self));
    }

    readFiles(files) {
        var self = this;
        var readfiles = {};
        Object.keys(files).forEach(function(key) {
            var file = files[key];
            var fr = new FileReader();
            fr.onload = function() {
                readfiles[key] = fr.result;
                if (Object.keys(files).length === Object.keys(readfiles).length) {
                    self.sendFileToServer(readfiles);
                }
            };
            fr.readAsDataURL(file);
        });
    }

    getFields() {
        var self = this;
        var fields = {};
        Object.keys(this.props.record.data).forEach(function(field) {
            var value = self.props.record.data[field];
            if (!value || field === 'omit_cfdi_related' || field === 'product_create') {
                fields[field] = value;
            } else if (Array.isArray(value)) {
                var valueList = [];
                value.data.forEach(function(val) {
                    valueList.push(val.data.id);
                });
                fields[field] = valueList;
            } else {
                fields[field] = value.data.id;
            }
        });
        return fields;
    }

    sendFileToServer(files) {
        var self = this;
        var options = self.getFields();
        var ctx = this.props.record.context;
        ctx.currentCompanyId = this.env.model.config.currentCompanyId;
        ctx.account_id = options.account_id;
        ctx.journal_id = options.journal_id;
        ctx.omit_cfdi_related = options.omit_cfdi_related;
        ctx.product_create = options.product_create;
        rpc(`/web/dataset/call_kw/multi.file.attach.xmls.wizard/check_xml`, {
            model: 'multi.file.attach.xmls.wizard',
            method: 'check_xml',
            args: [files],
            kwargs: {
                context: ctx,
            },
        }).then(function(result) {
            var wrongfiles = result.wrongfiles;
            var attachments = result.attachments;
            Object.keys(attachments).forEach(function(key) {
                var data = attachments[key];
                self.attachment_ids.push(data.attachment_id);
                self.files[key].iscorrect = true;
                self.createdCorrectly(key);
            });
            Object.keys(wrongfiles).forEach(function(key) {
                self.files[key].iscorrect = false;
            });
            if (Object.keys(wrongfiles).length > 0) {
                self.handleFileWrong(wrongfiles);
            }
            if (Object.keys(wrongfiles).length === 0 || self.alerts_in_queue.total === 0) {
                self.correctFinalRegistry();
            }
        });
    }

    createdCorrectly(key) {
        var self = this;
        var alert = document.querySelector('#filescontent div[title="' + key + '"]');
        alert.classList.add('xml_correct');
        alert.querySelector('div.remove_xml').innerHTML = '&#10004;';
    }

    handleFileWrong(wrongfiles) {
        this.alerts_in_queue = {
            alertHTML: {},
            total: Object.keys(wrongfiles).length,
        };
        const self = this;

        Object.keys(wrongfiles).forEach(function(key) {
            const file = wrongfiles[key];

            if ("cfdi_type" in file) {
                if (Object.keys(self.files).length === 0) {
                    self.restart();
                }
                self.alerts_in_queue.total -= 1;

                const fileElement = document.querySelector(`#filescontent div[title="${key}"]`);
                if (fileElement) {
                    fileElement.remove();
                }

                self.notification.add(
                    _t("XML removed, the TipoDeComprobante is not I nor E."), {
                        title: _t("Error"),
                        type: "danger"
                    }
                );
            } else {
                const alertParts = self.prepareWrongAlert(key, file);
                const alertElement = document.createElement("div");
                alertElement.setAttribute("tag", key);
                alertElement.className = `alert alert-${alertParts.alerttype} dnd-alert`;
                alertElement.innerHTML =
                    alertParts.errors +
                    '<div>' +
                    alertParts.buttons +
                    _t(
                        `<span>Wrong File: <span class="index-alert"></span>` +
                        `/${self.alerts_in_queue.total}` +
                        `<b style="font-size:15px;font-wight:900;">&#8226;</b> ${key}</span></div>`
                    );

                const removeXmlBtn = alertElement.querySelector("#remove_xml");
                if (removeXmlBtn) {
                    removeXmlBtn.addEventListener("click", self.remove_xml.bind(self));
                }

                const tryAgainBtn = alertElement.querySelector("#tryagain");
                if (tryAgainBtn) {
                    tryAgainBtn.addEventListener("click", self.remove_xml.bind(self));
                }

                const removeAllXmlBtn = alertElement.querySelector("#remove_all_xml");
                if (removeAllXmlBtn) {
                    removeAllXmlBtn.addEventListener("click", self.remove_all_xml.bind(self));
                }

                self.alerts_in_queue.alertHTML[key] = {
                    alert: alertElement,
                    xml64: file.xml64,
                };
            }

            if (
                self.alerts_in_queue.total > 0 &&
                self.alerts_in_queue.total === Object.keys(self.alerts_in_queue.alertHTML).length
            ) {
                self.nextWrongAlert();
            }
        });
    }

    prepareWrongAlert(key, data) {
        var self = this;
        var errors = '';
        var buttons = '';
        var able_buttons = [];
        var alerttype = '';
        if ('error' in data) {
            errors += self.wrongMsgServer(data, able_buttons);
            alerttype = 'danger';
        } else {
            errors += self.wrongMsgXml(data, able_buttons);
            alerttype = 'info';
        }
        if (able_buttons.includes('partner') && !able_buttons.includes('remove')) {
            buttons += _t('<button class="dnd-alert-button" tag="remove">Remove XML</button>') +
                _t('<button class="dnd-alert-button" tag="partner">Create Partner</button>');
        } else if (able_buttons.includes('tryagain')) {
            buttons += _t('<button id="remove_xml" class="dnd-alert-button remove" tag="remove" t-on-click="remove_xml">Remove XML</button>') +
                _t('<button class="dnd-alert-button" tag="tryagain" id="tryagain">Try again</button>');
        } else if (able_buttons.includes('remove')) {
            buttons += _t('<button class="dnd-alert-button" tag="remove" t-on-click="remove_xml">Remove XML</button>');
        }
        if (buttons.length > 0) {
            buttons += _t('<button id="remove_all_xml" class="dnd-alert-remove-all-wrong-xml-button" style="background-color: #31708f; border: 0px solid; margin: 0 5px 0 0; color: #ffffff;" tag="remove">Remove all wrong XML</button>');
        }
        return {
            'errors': errors,
            'buttons': buttons,
            'alerttype': alerttype
        };
    }

    wrongMsgServer(data, able_buttons) {
        var typemsg = {
            'CheckXML': _t('Error checking XML data.'),
            'CreatePartner': _t('Error creating partner.'),
            'CreateMove': _t('Error creating move.')
        };
        var errors = '<div><span level="2">' + data.error[0] + '</span> <span level="1">' + data.error[1] + '</span>.<br>' + typemsg[data.where] + '</div>';
        able_buttons.push('tryagain');
        return errors;
    }
    wrongMsgXml(file, able_buttons) {
        var self = this;
        var errors = '';
        var map_error = {
            unsigned: _t('<div><span level="1">UUID</span> not found in the XML.</div>'),
            version: _t('<div><span level="1">Unable to generate moves from an XML with version 3.2.</span>You can create the move manually and then attach the xml.</div>'),
            nothing: _t('<div><strong>Info!</strong> XML data could not be read correctly.</div>'),
        };
        Object.keys(file).forEach(function(ikey) {
            var val = file[ikey];
            if (ikey === 'wrong_company_r') {
                errors += _t('<div><span level="1">The XML Receptor RFC</span> does not match with <span level="1">your Company RFC</span>: ') +
                    _t('XML Receptor RFC: <span level="2">') + val[0] + _t(', </span> Your Company RFC: <span level="2">') + val[1] + '</span></div>';
                able_buttons.push('remove');
            }
            if (ikey === 'wrong_company_i') {
                errors += _t('<div><span level="1">The XML Issuer RFC</span> does not match with <span level="1">your Company RFC</span>: ') +
                    _t('XML Issuer RFC: <span level="2">') + val[0] + _t(', </span> Your Company RFC: <span level="2">') + val[1] + '</span></div>';
                able_buttons.push('remove');
            }
            if (ikey !== 'wrong_company_r' && ikey !== 'wrong_company_i' && ikey !== 'partner_not_found' && ikey !== 'xml64' && !able_buttons.includes('remove')) {
                able_buttons.push('remove');
            }
            if (ikey === 'partner_not_found') {
                errors += _t('<div><span level="1">The XML partner</span> was not found: <span level="2">') + val + '</span>.</div>';
                able_buttons.push('partner');
            }
            if (ikey === 'reference_multi') {
                errors += _t('<div><span level="1">The XML reference</span> matches another move reference. <span level="1">Partner: </span>') + val[0] + _t('<span level="1"> Reference: </span>') + val[1] + '</div>';
            }
            if (ikey === 'currency') {
                errors += _t('<div><span level="1">The XML Currency</span> <span level="2">') + val + _t('</span> was not found or is disabled.</div>');
            }
            if (ikey === 'taxes') {
                errors += _t('<div><span level="1">Some taxes</span> do not exist: <span level="2">') + val.join(', ') + '</span>.</div>';
            }
            if (ikey === 'taxes_wn_accounts') {
                errors += _t('<div><span level="1">Some taxes</span> do not have account assigned: <span level="2">') + val.join(', ') + '</span>.</div>';
            }
            if (ikey === 'uuid_duplicated') {
                errors += _t('<div><span level="1">The XML UUID</span> belong to other move. <span level="1">UUID: </span>') + val + '</div>';
            }
            if (ikey === 'cancelled') {
                errors += _t('<div><span level="1">The XML state</span> is CANCELLED in SATs system. ') +
                    _t('XML Folio: <span level="2">') + val[1] + '</span></div>';
                able_buttons.push('tryagain');
            }
            if (ikey === 'folio') {
                errors += _t('<div><span level="1">The XML Folio</span> does not match with <span level="1">Partner document number</span>: ') +
                    _t('XML Folio: <span level="2">') + val[0] + _t(', </span> Partner document number: <span level="2">') + val[1] + '</span></div>';
            }
            if (ikey === 'amount') {
                errors += _t('<div><span level="1">The XML amount total</span> does not match with <span level="1">move total</span>: ') +
                    _t('XML amount total: <span level="2">') + val[0] + _t(', </span> Move total: <span level="2">') + val[1] + '</span></div>';
                able_buttons.push('tryagain');
            }
            if (ikey === 'amount_tax') {
                errors += _t('<div><span level="1">The XML tax total amount</span> does not match with <span level="1">Move tax total amount</span>: ') +
                    _t('XML tax total: <span level="2">') + val[0] + _t(', </span> Move tax total: <span level="2">') + val[1] + '</span> Ref: ' + val[2] + '</div>';
                able_buttons.push('tryagain');
            }
            if (ikey === 'moves_related_not_found') {
                errors += _t('<div>The <span level="1">TipoDeComprobante</span> is <span level="1">"E"</span> and The XML UUIDs are not related to any move. <span level="1">UUID: </span>') + val + '</div>';
                able_buttons.push('tryagain');
            }
            if (ikey === 'no_node_related_uuids') {
                errors += _t('<div>The <span level="1">TipoDeComprobante</span> is <span level="1">"E"</span> and The node CFDI related is not set</span> Manually reconcile with the appropiate move. <span level="1">UUID: </span>') + val + '</div>';
            }
            if (ikey === 'invoice_not_found') {
                errors += _t('<div><span level="1">The DocumentType is "E" and The XML UUID</span> is not related to any invoice. <span level="1">UUID: </span>') + val + '</div>';
            }
            if (Object.prototype.hasOwnProperty.call(map_error, ikey)) {
                errors += map_error[ikey];
            }
        });
        return errors;
    }

    sendErrorToServer(xml64, key, function_def) {
        /* Sends again the base64 file string to the server to retry to create the move, or
        sends the partner's data to be created in db if does not exist */
        var self = this;
        var xml_file = {};
        xml_file[key] = xml64;
        var options = self.getFields();
        var ctx = self.env.model.root.context;
        ctx.account_id = options.account_id;
        rpc("/web/dataset/call_kw/multi.file.attach.xmls.wizard/" + function_def, {
            model: 'multi.file.attach.xmls.wizard',
            method: function_def,
            args: [xml_file],
            kwargs: {
                context: ctx,
            },
        }).then(function(data) {
            var wrongfiles = data.wrongfiles;
            var attachments = data.attachments;
            Object.keys(attachments).forEach(function(rkey) {
                var result = attachments[rkey];
                var alertobj = document.querySelector('#alertscontent div[tag="' + rkey + '"].alert.dnd-alert');
                self.attachment_ids.push(result.attachment_id);
                self.createdCorrectly(rkey);
                self.removeWrongAlerts(alertobj, rkey, false);
            });
            Object.keys(wrongfiles).forEach(function(rkey) {
                var result = wrongfiles[rkey];
                var alert_parts = self.prepareWrongAlert(rkey, result);
                var alertobj = document.querySelector('#alertscontent div[tag="' + rkey + '"].alert.dnd-alert');
                var footer = alertobj.querySelector('div:last-child span:not(.index-alert)');
                alertobj.classList.remove('alert-danger', 'alert-info');
                alertobj.classList.add('alert-' + alert_parts.alerttype);
                alertobj.innerHTML = alert_parts.errors + '<div>' + alert_parts.buttons + '</div>';
                alertobj.querySelector('div:last-child').appendChild(footer);
            });
        });
    }

    removeWrongAlerts(alertobj, filekey, removefile) {
        /* Removes the current error alert to continue with the others */
        var self = this;
        alertobj.style.display = 'none';
        delete self.alerts_in_queue.alertHTML[filekey];
        if (removefile) {
            delete self.files[filekey];
            var fileElement = document.querySelector('#filescontent div[title="' + filekey + '"]');
            fileElement.style.opacity = '0';
            setTimeout(function() {
                fileElement.remove();
                self.continueAlert(alertobj);
            }, 500);
        } else {
            self.continueAlert(alertobj);
        }
    }

    continueAlert(alertobj) {
        /* After the error alert is removed, execute the next actions
        (Next error alert, Restarts to attach more files, or Shows the final success alert) */
        var self = this;
        alertobj.remove();
        if (self.alerts_in_queue.alertHTML && Object.keys(self.alerts_in_queue.alertHTML).length > 0) {
            self.nextWrongAlert();
        } else if (Object.keys(self.files).length === 0) {
            self.restart();
        } else {
            self.correctFinalRegistry();
        }
    }

    nextWrongAlert() {
        /* Shows the next error alert */
        var self = this;
        var keys = Object.keys(self.alerts_in_queue.alertHTML);
        var alert = self.alerts_in_queue.alertHTML[keys[0]].alert;
        alert.style.display = 'none';
        alert.querySelector('div:last-child .index-alert').innerHTML = self.alerts_in_queue.total - (keys.length - 1);
        document.getElementById('alertscontent').appendChild(alert);
        alert.style.display = 'block';
    }

    restart() {
        /* Restarts all the variables and restores all the DOM element to attach more new files */
        this.files = {};
        this.attachment_ids = [];
        this.uploading_files = false;
        this.alerts_in_queue = {};
        document.getElementById("dragandrophandler").style.display = 'block';
        document.getElementById("filescontent").innerHTML = '';
        document.getElementById("files").value = '';
        document.querySelector('#dndfooter button#save').disabled = false;
        document.querySelectorAll('#alertscontent div.alert').forEach(function(alert) {
            alert.remove();
        });
        document.querySelector('#dndfooter button#show').style.display = 'none';
    }

    correctFinalRegistry() {
        /* Shows the final success alert and the button to see the moves created */
        var self = this;
        var alert = document.createElement('div');
        alert.className = 'alert alert-success dnd-alert';
        alert.innerHTML = _t('Your moves were created correctly') + '.';
        alert.style.display = 'none';
        document.getElementById('alertscontent').appendChild(alert);
        alert.style.display = 'block';
        document.querySelector('#dndfooter').querySelector("#show").style.display = 'block';
    }
}
IbanWidget.template = "l10n_mx_sat_sync_itadmin_ee.multi_attach_xmls_template";

export const ibanWidget = {
    ...charField,
    component: IbanWidget,
};

registry.category("fields").add("multi_attach_xmls_wizard_widget", ibanWidget);
