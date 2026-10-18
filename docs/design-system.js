/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';

    function initializeNavigation() {
        const links = Array.from(document.querySelectorAll('[data-lab-navigation] a[data-lab-destination]'));
        const views = Array.from(document.querySelectorAll('section[data-lab-view]'));
        if (!links.length || !views.length) return;
        const destinations = new Map(views.map(view => [view.dataset.labView, view]));

        function hashDestination() {
            // Old shell/dashboard bookmarks resolve to the consolidated home view.
            if (['#shell', '#dashboard'].includes(location.hash)) return 'home';
            return links.find(link => link.hash === location.hash)?.dataset.labDestination;
        }

        function activate(destination, updateHash = false) {
            const selected = destinations.get(destination);
            if (!selected) return;
            views.forEach(view => { view.hidden = view !== selected; });
            links.forEach(link => {
                if (link.dataset.labDestination === destination) link.setAttribute('aria-current', 'page');
                else link.removeAttribute('aria-current');
            });
            // These links choose a contained example, rather than scrolling
            // the catalogue or moving keyboard focus into its contents.
            if (updateHash) {
                const target = new URL(location.href);
                target.hash = selected.id;
                history.replaceState(history.state, '', target.href);
            }
        }

        links.forEach(link => link.addEventListener('click', event => {
            if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            if (!destinations.has(link.dataset.labDestination)) return;
            event.preventDefault();
            activate(link.dataset.labDestination, true);
        }));
        document.querySelectorAll('[data-lab-feature-link]').forEach(link => link.addEventListener('click', event => {
            if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            // Reveal the destination before native fragment scrolling. These
            // public preview links keep normal URL/history and keyboard behavior.
            activate(link.dataset.labFeatureLink);
        }));
        // Native history restores scrolling after popstate and before
        // hashchange. Reveal the destination before that restoration, while
        // keeping fragment navigation and the browser's saved position native.
        window.addEventListener('popstate', () => activate(hashDestination()));
        window.addEventListener('hashchange', () => activate(hashDestination()));
        activate(hashDestination() || 'home');
        document.querySelector('[data-lab-navigation]').dataset.labEnhanced = 'true';
    }

    function initializeTransactionPreview() {
        const form = document.getElementById('lab-transaction-form');
        const result = document.getElementById('lab-entry-result');
        if (!form || !result) return;
        const names = ['type', 'title', 'amount', 'date', 'category', 'payment', 'account', 'credit', 'debit'];
        const fields = Object.fromEntries(names.map(name => [name, document.getElementById(`lab-entry-${name}`)]));
        const errors = Object.fromEntries(names.map(name => [name, form.querySelector(`[data-lab-error-for="${name}"]`)]));
        if (names.some(name => !fields[name] || !errors[name])) return;
        const radioNames = {type: 'type', payment: 'payment_method', credit: 'credit_card', debit: 'debit_card'};
        const methods = ['ACCOUNT', 'PIX', 'DEBIT_CARD', 'CREDIT_CARD'];
        const methodLabels = {ACCOUNT: 'Account transfer', PIX: 'Pix', DEBIT_CARD: 'Debit card', CREDIT_CARD: 'Credit card'};
        const integerFormat = new Intl.NumberFormat('en-US', {maximumFractionDigits: 0});
        let previousMethod = '';

        // This static example handles its own errors; native GETs remain the
        // no-JavaScript path and never create a financial record.
        form.noValidate = true;
        form.dataset.labEnhanced = 'true';
        function radios(name) { return Array.from(fields[name].querySelectorAll(`input[name="${radioNames[name]}"]`)); }
        function selected(name) { return radios(name).find(input => input.checked && !input.disabled); }
        function value(name) { return selected(name)?.value || ''; }
        function clearRadios(name) { radios(name).forEach(input => { input.checked = false; }); }
        function enhancedInput(field) {
            if (!field?.matches('select[data-search-select]')) return null;
            return document.getElementById(field.dataset.searchId || `${field.id}-search`);
        }
        function focusControl(field) {
            if (!field) return;
            // Expose invalid fields, but keep a cancelled disclosure closed
            // when returning keyboard focus to its own summary.
            for (let parent = field.parentElement; parent; parent = parent.parentElement) {
                if (parent.tagName === 'DETAILS' && parent.firstElementChild !== field) parent.open = true;
            }
            const control = enhancedInput(field) || (field.tagName === 'FIELDSET'
                ? field.querySelector('input:not(:disabled), select:not(:disabled), button:not(:disabled)') : field);
            if (!control) return;
            control.focus({preventScroll: true});
            control.scrollIntoView({block: 'nearest', behavior: 'instant'});
        }
        function describeError(control, error, message) {
            const descriptions = new Set((control.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
            descriptions.delete(error.id);
            if (message) {
                control.setAttribute('aria-invalid', 'true');
                if (error.id) descriptions.add(error.id);
            } else control.removeAttribute('aria-invalid');
            if (descriptions.size) control.setAttribute('aria-describedby', [...descriptions].join(' '));
            else control.removeAttribute('aria-describedby');
        }
        function setError(name, message) {
            const error = errors[name];
            error.textContent = message;
            error.hidden = !message;
            [fields[name], enhancedInput(fields[name]), ...(radioNames[name] ? radios(name) : [])]
                .filter(Boolean).forEach(control => describeError(control, error, message));
        }
        function clearResult() {
            result.textContent = '';
            delete result.dataset.labState;
        }
        function decimalAmount(input) {
            const text = input.trim();
            if (!/^\d+(?:[.,]\d{1,2})?$/.test(text)) return null;
            const [whole, fraction = ''] = text.split(/[.,]/);
            const cents = fraction.padEnd(2, '0');
            const integer = BigInt(whole);
            if (integer === 0n && cents === '00') return null;
            // Keep submitted cents exact instead of rounding through Number.
            return `${integerFormat.format(integer)}.${cents}`;
        }
        function validDate(input) {
            if (!/^\d{4}-\d{2}-\d{2}$/.test(input)) return false;
            const parsed = new Date(`${input}T00:00:00Z`);
            return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === input;
        }
        function activateGroup(group, active) {
            group.hidden = !active;
            group.querySelectorAll('input, select, textarea, button').forEach(control => { control.disabled = !active; });
        }
        function accountAllowed(option, method) {
            return Boolean(option?.value && (method !== 'PIX' || option.dataset.pix === 'true'));
        }
        function updateContext(deliberate = false) {
            const kind = value('type');
            const hasKind = ['EXPENSE', 'INCOME'].includes(kind);
            form.querySelectorAll('[data-lab-kind-context]').forEach(group => activateGroup(group, hasKind));
            form.querySelectorAll('[data-lab-payment-option]').forEach(option => {
                const allowed = hasKind && (kind === 'EXPENSE' || !['DEBIT_CARD', 'CREDIT_CARD'].includes(option.dataset.labPaymentOption));
                option.hidden = !allowed;
                option.querySelectorAll('input').forEach(input => {
                    input.disabled = !allowed;
                    if (!allowed && deliberate) input.checked = false;
                });
            });
            const method = value('payment');
            Array.from(fields.category.options).forEach(option => {
                const incompatible = Boolean(option.value && (!hasKind || option.dataset.labKind !== kind));
                option.disabled = incompatible;
                option.hidden = incompatible;
            });
            if (deliberate && fields.category.value && fields.category.selectedOptions[0]?.dataset.labKind !== kind) {
                fields.category.value = '';
                setError('category', '');
            }
            form.querySelectorAll('[data-lab-source]').forEach(group => {
                activateGroup(group, hasKind && Boolean(method) && group.dataset.labSource.split(/\s+/).includes(method));
            });
            const usesAccount = hasKind && ['ACCOUNT', 'PIX'].includes(method);
            Array.from(fields.account.options).forEach(option => {
                const incompatible = Boolean(option.value && !accountAllowed(option, method));
                option.disabled = incompatible;
                option.hidden = incompatible;
            });
            if (deliberate) {
                if (!usesAccount || (fields.account.value && !accountAllowed(fields.account.selectedOptions[0], method))) {
                    fields.account.value = '';
                    setError('account', '');
                }
                if (method !== 'CREDIT_CARD') { clearRadios('credit'); setError('credit', ''); }
                if (method !== 'DEBIT_CARD') { clearRadios('debit'); setError('debit', ''); }
                if (previousMethod !== method) setError('payment', '');
            }
            fields.category.required = hasKind;
            fields.account.required = usesAccount;
            radios('payment').forEach(input => { input.required = hasKind && !input.disabled; });
            radios('credit').forEach(input => { input.required = method === 'CREDIT_CARD'; });
            radios('debit').forEach(input => { input.required = method === 'DEBIT_CARD'; });
            if (!hasKind) ['category', 'payment', 'account', 'credit', 'debit'].forEach(name => setError(name, ''));
            const paymentLabel = form.querySelector('[data-lab-payment-label]');
            if (paymentLabel) paymentLabel.textContent = kind === 'INCOME' ? 'Received via' : 'Payment method';
            const label = form.querySelector('[data-lab-account-label]');
            if (label) label.textContent = kind === 'INCOME' ? 'Received into' : 'Paid from';
            previousMethod = method;
            updateEditorAvailability();
            window.TuxedoForms?.refresh(form);
            const search = enhancedInput(fields.account);
            const accountLabel = label?.closest('label')?.textContent.trim();
            if (search && accountLabel) {
                document.getElementById(search.getAttribute('aria-controls'))?.setAttribute('aria-label', accountLabel);
                const clearText = document.querySelector('[data-form-ui-strings]')?.dataset.clear || 'Clear selection';
                search.parentElement.querySelector('button')?.setAttribute('aria-label', `${clearText}: ${accountLabel}`);
            }
        }
        function message(name) {
            const kind = value('type'), method = value('payment');
            if (name === 'type') return kind ? '' : 'Choose an entry type for this example.';
            if (name === 'title') return fields.title.value.trim() ? '' : 'Enter a title for this example.';
            if (name === 'amount') return decimalAmount(fields.amount.value) ? '' : 'Enter a positive amount with up to two decimal places.';
            if (name === 'date') return validDate(fields.date.value) ? '' : 'Choose a valid date for this example.';
            if (!kind) return '';
            if (name === 'category') {
                const option = fields.category.selectedOptions[0];
                return option?.value && !option.disabled && option.dataset.labKind === kind ? '' : 'Choose a category for the selected entry type.';
            }
            if (name === 'payment') return methods.includes(method) && !(kind === 'INCOME' && method.endsWith('_CARD'))
                ? '' : 'Choose a payment method for this example.';
            if (name === 'account' && ['ACCOUNT', 'PIX'].includes(method)) return accountAllowed(fields.account.selectedOptions[0], method)
                ? '' : method === 'PIX' ? 'Choose an account with Pix enabled.' : 'Choose an account for this example.';
            if (name === 'credit' && method === 'CREDIT_CARD') return selected('credit') ? '' : 'Choose a credit card for this example.';
            if (name === 'debit' && method === 'DEBIT_CARD') return selected('debit') ? '' : 'Choose a debit card for this example.';
            return '';
        }
        form.addEventListener('submit', event => {
            event.preventDefault();
            clearResult();
            let firstInvalid;
            names.forEach(name => {
                const error = message(name);
                setError(name, error);
                if (error && !firstInvalid) firstInvalid = fields[name];
            });
            window.TuxedoForms?.refresh(form);
            if (firstInvalid) { focusControl(firstInvalid); return; }
            const method = value('payment');
            const card = selected(method === 'CREDIT_CARD' ? 'credit' : 'debit')?.closest('[data-card-id]');
            const instrument = ['ACCOUNT', 'PIX'].includes(method) ? fields.account.selectedOptions[0].textContent.trim()
                : card?.dataset.cardName || card?.querySelector('[data-card-name]')?.textContent.trim() || 'Example card';
            result.dataset.labState = 'created';
            result.textContent = `Preview created: ${fields.title.value.trim()} · BRL ${decimalAmount(fields.amount.value)} · ${methodLabels[method]} · ${instrument}. Nothing has been saved.`;
        });
        function edit(event) {
            if (event.target.form !== form || editor?.contains(event.target)) return;
            clearResult();
            if (event.type === 'change' && ['type', 'payment_method'].includes(event.target.name)) updateContext(true);
            const name = names.find(name => fields[name] === event.target || enhancedInput(fields[name]) === event.target
                || (radioNames[name] && radioNames[name] === event.target.name));
            if (name && !errors[name].hidden && !message(name)) setError(name, '');
        }
        form.addEventListener('input', edit);
        form.addEventListener('change', edit);
        form.addEventListener('reset', () => {
            clearResult();
            names.forEach(name => setError(name, ''));
            // A transaction reset does not remove locally created card specimens.
            // Wait for native reset before syncing the shared searchable choices.
            setTimeout(() => {
                Object.keys(radioNames).forEach(clearRadios);
                fields.category.value = fields.account.value = '';
                updateContext();
            }, 0);
        });

        const editor = document.getElementById('lab-card-editor');
        const cardForm = document.getElementById('lab-card-form');
        const cardList = document.getElementById('lab-credit-card-choices');
        const cardPreview = document.getElementById('lab-card-preview');
        const cardError = document.getElementById('lab-card-error');
        const cardKeys = ['bank', 'account', 'name', 'type', 'closing', 'due', 'manual', 'color', 'gradient', 'end', 'angle'];
        const cardFields = Object.fromEntries(cardKeys.map(key => [key, document.getElementById(`lab-card-${key}`)]));
        const hasEditor = editor && cardForm && cardList && cardPreview && cardError && cardKeys.every(key => cardFields[key]);
        const presets = {GRAPHITE: '#253330', PLUM: '#5B3E7C', COPPER: '#C6A173', FOREST: '#315D50'};
        let editingCard = null;
        let nextCardId = 5001;
        function presetInputs() { return hasEditor ? Array.from(editor.querySelectorAll('input[name="card_preset"]')) : []; }
        function presetColor(input) { return presets[input?.value?.toUpperCase()] || safeColor(input?.value); }
        function safeColor(color) { return /^#[0-9a-f]{6}$/i.test(color || '') ? color.toUpperCase() : '#253330'; }
        function optionText(field, key) { return Array.from(field.options).find(option => option.value === key)?.textContent.trim() || ''; }
        function updateEditorAvailability(clearAccount = false) {
            if (!hasEditor) return;
            const available = value('type') === 'EXPENSE' && value('payment') === 'CREDIT_CARD';
            editor.querySelectorAll('input, select, textarea, button').forEach(control => { control.disabled = !available; });
            // Shared search controls must inherit the select's external form:
            // Enter in this editor must never submit the surrounding entry.
            [cardFields.bank, cardFields.account].forEach(field => {
                const input = enhancedInput(field);
                if (!input) return;
                input.setAttribute('form', cardForm.id);
                input.parentElement.querySelector('button')?.setAttribute('form', cardForm.id);
            });
            const bank = cardFields.bank.value;
            Array.from(cardFields.account.options).forEach(option => {
                const incompatible = Boolean(option.value && (!bank || option.dataset.bank !== bank));
                option.hidden = incompatible;
                option.disabled = incompatible;
            });
            if (clearAccount && cardFields.account.selectedOptions[0]?.dataset.bank !== bank) cardFields.account.value = '';
            cardFields.account.disabled = !available || !bank;
            const accountGroup = cardFields.account.closest('.lab-field');
            if (accountGroup) accountGroup.hidden = !bank;
            editor.querySelectorAll('[data-lab-card-account-context]').forEach(group => { group.hidden = !bank; });
            editor.querySelectorAll('[data-lab-card-edit-only]').forEach(group => {
                group.hidden = !editingCard;
                if ('disabled' in group) group.disabled = !available || !editingCard;
                group.querySelectorAll('input, select, textarea, button').forEach(control => { control.disabled = !available || !editingCard; });
            });
            editor.querySelectorAll('[data-lab-gradient-context]').forEach(group => {
                const active = available && editingCard && cardFields.gradient.checked;
                group.hidden = !editingCard || !cardFields.gradient.checked;
                group.querySelectorAll('input, select').forEach(control => { control.disabled = !active; });
            });
            window.TuxedoForms?.refresh(editor);
        }
        function readCard(label) {
            const data = label.dataset;
            return {id: data.cardId, name: data.cardName || label.querySelector('[data-card-name]')?.textContent.trim() || 'Example card',
                bank: data.cardBank || '', account: data.cardAccount || '', type: data.cardType || 'PHYSICAL',
                closing: data.cardClosing || '', due: data.cardDue || '', manual: data.cardManual || '',
                color: safeColor(data.cardColor), gradient: data.cardGradient === 'true',
                end: safeColor(data.cardEnd || data.cardColor), angle: ['0', '45', '90', '135'].includes(data.cardAngle) ? data.cardAngle : '45'};
        }
        function editorRecord() {
            const preset = presetColor(presetInputs().find(input => input.checked));
            return {id: editingCard?.dataset.cardId || '', name: cardFields.name.value.trim(), bank: cardFields.bank.value,
                account: cardFields.account.value, type: cardFields.type.value, closing: cardFields.closing.value,
                due: cardFields.due.value, manual: cardFields.manual.value, color: editingCard ? safeColor(cardFields.color.value) : preset,
                gradient: Boolean(editingCard && cardFields.gradient.checked), end: safeColor(cardFields.end.value), angle: cardFields.angle.value};
        }
        function luminance(color) {
            const channels = color.slice(1).match(/.{2}/g).map(channel => parseInt(channel, 16) / 255)
                .map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4);
            return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
        }
        function contrast(first, second) { const a = luminance(first), b = luminance(second); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05); }
        function renderCard(target, record) {
            const start = safeColor(record.color), end = record.gradient ? safeColor(record.end) : start;
            const channels = color => color.slice(1).match(/.{2}/g).map(channel => parseInt(channel, 16));
            const first = channels(start), last = channels(end);
            // Different light stops can still produce a darker middle. Check
            // the local gradient before choosing unprotected foreground text.
            const samples = Array.from({length: 11}, (_, index) => '#' + first.map((channel, position) =>
                Math.round(channel + (last[position] - channel) * index / 10).toString(16).padStart(2, '0')).join(''));
            const white = Math.min(...samples.map(color => contrast('#FFFFFF', color)));
            const dark = Math.min(...samples.map(color => contrast('#101E18', color)));
            const ink = white >= dark ? '#FFFFFF' : '#101E18';
            target.style.setProperty('--card-start', start);
            target.style.setProperty('--card-end', end);
            target.style.setProperty('--card-angle', `${['0', '45', '90', '135'].includes(record.angle) ? record.angle : '45'}deg`);
            target.style.setProperty('--card-ink', ink);
            target.dataset.cardProtected = String(Math.max(white, dark) < 4.5);
            target.querySelectorAll('[data-card-name]').forEach(node => { node.textContent = record.name || 'Card name'; });
            const context = [optionText(cardFields.bank, record.bank), optionText(cardFields.account, record.account)].filter(Boolean).join(' · ');
            target.querySelectorAll('[data-card-context]').forEach(node => { node.textContent = context || 'Choose a bank and account'; });
            target.querySelectorAll('[data-card-type-label]').forEach(node => { node.textContent = record.type.charAt(0) + record.type.slice(1).toLowerCase(); });
        }
        function saveCardData(label, record) {
            for (const [key, entry] of Object.entries(record)) label.dataset[`card${key.charAt(0).toUpperCase()}${key.slice(1)}`] = String(entry);
            renderCard(label, record);
        }
        function showCardError(key, message) {
            const field = cardFields[key];
            const error = editor.querySelector(`[data-lab-card-error-for="${key}"]`) || cardError;
            if (error !== cardError) { error.textContent = message; error.hidden = !message; }
            if (field) [field, enhancedInput(field)].filter(Boolean).forEach(control => describeError(control, error, message));
        }
        function setCardSummary(message) {
            // Empty static placeholders must not make the shared form enhancer
            // open this native disclosure as though it contained a bound error.
            if (message) cardError.setAttribute('role', 'alert');
            else cardError.removeAttribute('role');
            cardError.textContent = message;
            cardError.hidden = !message;
        }
        function clearCardErrors() {
            setCardSummary('');
            cardKeys.forEach(key => showCardError(key, ''));
        }
        function resetEditor() {
            if (!hasEditor) return;
            editingCard = null;
            ['bank', 'account', 'name', 'closing', 'due', 'manual'].forEach(key => { cardFields[key].value = ''; });
            cardFields.type.value = 'PHYSICAL';
            cardFields.color.value = cardFields.end.value = '#253330';
            cardFields.gradient.checked = false;
            cardFields.angle.value = '45';
            presetInputs().forEach((input, index) => { input.checked = presetColor(input) === '#253330' || (!index && !presetInputs().some(item => presetColor(item) === '#253330')); });
            editor.querySelector('[data-lab-card-editor-title]').textContent = 'New card';
            editor.querySelectorAll('details.lab-card-cycle').forEach(details => { details.open = false; });
            editor.querySelector('[data-lab-card-submit]').textContent = 'Preview card';
            clearCardErrors();
            updateEditorAvailability();
            renderCard(cardPreview, editorRecord());
        }
        function openCard(label) {
            editingCard = label;
            const record = readCard(label);
            cardKeys.forEach(key => {
                if (key === 'gradient') cardFields[key].checked = record.gradient;
                else cardFields[key].value = record[key] || '';
            });
            presetInputs().forEach(input => { input.checked = presetColor(input) === record.color; });
            editor.querySelector('[data-lab-card-editor-title]').textContent = 'Edit card';
            editor.querySelector('[data-lab-card-submit]').textContent = 'Update preview';
            clearCardErrors();
            updateEditorAvailability();
            renderCard(cardPreview, record);
            editor.open = true;
            editor.querySelectorAll('details.lab-card-cycle').forEach(details => { details.open = true; });
            focusControl(cardFields.name);
        }
        function cardMessages() {
            const record = editorRecord();
            const day = input => /^\d{1,2}$/.test(input) && Number(input) >= 1 && Number(input) <= 31;
            return {bank: record.bank && cardFields.bank.selectedOptions[0] && !cardFields.bank.selectedOptions[0].disabled ? '' : 'Choose a bank for this card.',
                account: record.account && !cardFields.account.selectedOptions[0]?.disabled && cardFields.account.selectedOptions[0]?.dataset.bank === record.bank ? '' : 'Choose an account belonging to the selected bank.',
                name: record.name && record.name.length <= 100 ? '' : 'Enter a card name with up to 100 characters.',
                type: ['PHYSICAL', 'VIRTUAL', 'ADDITIONAL'].includes(record.type) ? '' : 'Choose a card type.',
                closing: day(record.closing) ? '' : 'Enter a closing day from 1 to 31.',
                due: day(record.due) ? '' : 'Enter a due day from 1 to 31.',
                manual: !record.manual || validDate(record.manual) ? '' : 'Choose a valid manual settlement date.'};
        }
        if (hasEditor) {
            cardForm.noValidate = true;
            editor.open = false;
            resetEditor();
            cardList.querySelectorAll('label[data-card-id]').forEach(label => saveCardData(label, readCard(label)));
            form.addEventListener('click', event => {
                const button = event.target.closest('[data-lab-edit-card]');
                if (!button) return;
                const label = Array.from(cardList.querySelectorAll('label[data-card-id]')).find(item => item.dataset.cardId === button.dataset.labEditCard);
                if (label) { event.preventDefault(); openCard(label); }
            });
            editor.querySelectorAll('[data-lab-card-cancel]').forEach(button => button.addEventListener('click', () => {
                editor.open = false;
                resetEditor();
                focusControl(editor.querySelector('summary'));
            }));
            function editCard(event) {
                // Shared search inputs live next to externally associated
                // selects; their DOM events still belong to this editor.
                if (!event.target.matches('input, select, textarea')) return;
                if (event.type === 'change' && event.target.name === 'card_preset') {
                    cardFields.color.value = cardFields.end.value = presetColor(event.target);
                    cardFields.gradient.checked = false;
                }
                updateEditorAvailability(event.type === 'change' && event.target === cardFields.bank);
                renderCard(cardPreview, editorRecord());
                const messages = cardMessages();
                for (const key of cardKeys) if (cardFields[key].getAttribute('aria-invalid') === 'true' && !messages[key]) showCardError(key, '');
                const remaining = Object.keys(messages).filter(key => messages[key] && cardFields[key].getAttribute('aria-invalid') === 'true');
                setCardSummary(remaining.length ? 'Review the card details. ' + messages[remaining[0]] : '');
            }
            editor.addEventListener('input', editCard);
            editor.addEventListener('change', editCard);
            cardForm.addEventListener('submit', event => {
                event.preventDefault();
                clearCardErrors();
                const messages = cardMessages();
                const invalid = Object.keys(messages).filter(key => messages[key]);
                invalid.forEach(key => showCardError(key, messages[key]));
                if (invalid.length) {
                    setCardSummary('Review the card details. ' + messages[invalid[0]]);
                    focusControl(cardFields[invalid[0]]);
                    return;
                }
                const record = editorRecord();
                let label = editingCard;
                if (!label) {
                    const sample = cardList.querySelector('.lab-card-choice');
                    if (!sample) return;
                    const choice = sample.cloneNode(true);
                    choice.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
                    label = choice.querySelector('label.lab-card-option');
                    const input = label.querySelector('input[name="credit_card"]');
                    do { record.id = String(nextCardId++); } while (cardList.querySelector(`input[value="${record.id}"]`));
                    input.value = record.id;
                    input.id = `lab-entry-credit-${record.id}`;
                    input.checked = input.defaultChecked = false;
                    input.disabled = false;
                    input.required = true;
                    input.removeAttribute('aria-invalid');
                    label.htmlFor = input.id;
                    const editButton = choice.querySelector('[data-lab-edit-card]');
                    editButton.dataset.labEditCard = record.id;
                    cardList.append(choice);
                }
                saveCardData(label, record);
                const button = label.closest('.lab-card-choice').querySelector('[data-lab-edit-card]');
                button.setAttribute('aria-label', `Edit ${record.name}`);
                clearResult();
                editor.open = false;
                resetEditor();
                focusControl(label.querySelector('input[name="credit_card"]'));
            });
        }
        Object.keys(radioNames).forEach(clearRadios);
        fields.category.value = fields.account.value = '';
        updateContext();
    }

    function initializeBowtie() {
        window.TuxedoPaperLayers?.initialize(document.querySelector('[data-lab-bowtie]'));
    }

    function initializePeriodExample() {
        document.querySelectorAll('[data-lab-period-example]').forEach(example => {
            const today = new Date();
            let offset = 0;
            const reset = example.querySelector('[data-lab-period-reset]');
            function render() {
                const month = new Date(today.getFullYear(), today.getMonth() + offset, 1);
                example.querySelector('[data-lab-period-label]').textContent = new Intl.DateTimeFormat('en', {month: 'long', year: 'numeric'}).format(month);
                example.querySelector('[data-lab-period-context]').textContent = offset === 0 ? 'This month' : offset > 0 ? 'Planned month' : 'Completed month';
                reset.hidden = offset === 0;
            }
            example.querySelectorAll('[data-lab-period-step]').forEach(button => button.addEventListener('click', () => {
                offset += Number(button.dataset.labPeriodStep);
                render();
            }));
            reset.addEventListener('click', () => { offset = 0; render(); });
            render();
        });
    }

    function initialize() {
        initializePeriodExample();
        // Old catalogue bookmarks resolve to the sole illustration without
        // carrying the retired experiment selector into subsequent links.
        const url = new URL(location.href);
        if (url.searchParams.has('bowtie')) {
            url.searchParams.delete('bowtie');
            history.replaceState(history.state, '', url.href);
        }
        // Defer scripts can run before DOMContentLoaded. Initialize shared
        // choices before disabling the example's initially inactive controls,
        // because the shared enhancer deliberately skips disabled selects.
        window.TuxedoForms?.init();
        initializeNavigation();
        initializeTransactionPreview();
        window.TuxedoLabCalendar?.initialize();
        initializeBowtie();

    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
    else initialize();
}());
