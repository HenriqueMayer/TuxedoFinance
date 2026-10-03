/* SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0 */
(function () {
    'use strict';
    if (window.TuxedoChartSelection) return;
    const initialized = new WeakSet(), active = new Map(), cache = new Map();
    let serial = 0, hovered = null, controlDismissed = false;
    function initialize() {
        for (const [root, state] of active) if (!root.isConnected) {state.close(); state.popover.remove(); active.delete(root);}
        // HTMX history restores cached HTML, not the original panel nodes.
        const panels=new Set(Array.from(active.values(),state=>state.popover));
        document.querySelectorAll('.chart-composition').forEach(panel=>{if(!panels.has(panel))panel.remove();});
        document.querySelectorAll('[data-chart-selection]').forEach(root => {
            if (initialized.has(root)) return;
            const controls = root.querySelector('[data-selection-controls]'), surface = root.querySelector('[data-selection-surface]');
            if (!controls || !surface) return;
            const config = JSON.parse(controls.querySelector('script').textContent);
            if (!config.points.length) return;
            initialized.add(root);
            const marks = Array.from(root.querySelectorAll('[data-point]'));
            const summary = controls.querySelector('[data-selection-summary]'), values = controls.querySelector('[data-selection-values]');
            const isSvg = surface.tagName.toLowerCase() === 'svg', linear = config.points[0].x !== undefined;
            const donut = config.mode === 'donut', items = donut || config.mode === 'items' || !linear;
            const center = root.querySelector('[data-donut-total]'), centerLabel = root.querySelector('[data-donut-label]');
            const originalCenter = center?.textContent, originalLabel = centerLabel?.textContent;
            const instruction = controls.querySelector('[data-chart-instructions]');
            instruction.id = 'chart-interaction-' + (++serial);
            surface.setAttribute('aria-describedby', instruction.id);
            marks.forEach(mark => {
                mark.setAttribute('tabindex', '0');mark.setAttribute('role', 'button');mark.setAttribute('aria-pressed', 'false');
                mark.setAttribute('aria-describedby', instruction.id);
                if (!mark.hasAttribute('aria-label')) mark.setAttribute('aria-label', config.points[Number(mark.dataset.point)].label + ' · ' + config.series[Number(mark.dataset.series)]);
            });
            let selected = new Set(), range = null, keyboardAnchor = null;
            let highlight;
            if (isSvg && linear) {
                highlight = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                for (const [key,value] of Object.entries({y:16,height:180,'pointer-events':'none',class:'fill-caramel/15 stroke-caramel',hidden:''})) highlight.setAttribute(key,value);
                surface.insertBefore(highlight,surface.querySelector('[data-chart-layer]'));
            }
            function money(cents, currency=controls.dataset.currency) {
                const negative=cents<0n, absolute=negative?-cents:cents, locale=document.documentElement.lang||'en';
                const separator=new Intl.NumberFormat(locale).formatToParts(1.1).find(part=>part.type==='decimal').value;
                return currency+' '+(negative?'−':'')+new Intl.NumberFormat(locale).format(absolute/100n)+separator+String(absolute%100n).padStart(2,'0');
            }
            const key = mark => mark.dataset.point+':'+mark.dataset.series;
            function render() {
                summary.hidden = selected.size===0 || donut;
                highlight?.setAttribute('hidden','');
                marks.forEach(mark=>{const on=selected.has(key(mark));mark.toggleAttribute('data-chart-selected',on);mark.setAttribute('aria-pressed',String(on));});
                if (donut) {
                    center.textContent=selected.size ? money([...selected].reduce((sum,id)=>{const [i,s]=id.split(':').map(Number);return sum+BigInt(config.points[i].values[s]);},0n)) : originalCenter;
                    centerLabel.textContent=selected.size ? controls.dataset.selectedLabel : originalLabel;
                    return;
                }
                if (!selected.size) return;
                const indices=[...new Set([...selected].map(id=>Number(id.split(':')[0])))].sort((a,b)=>a-b);
                let totals;
                if (config.mode==='change') {
                    const first=indices[0],last=indices[indices.length-1];
                    const opening=BigInt(first?config.points[first-1].values[0]:config.opening),closing=BigInt(config.points[last].values[0]);
                    totals=[['change',closing-opening],['opening',opening],['closing',closing]].map(([name,value])=>[controls.querySelector('[data-selection-'+name+']').textContent,value]);
                } else {
                    totals=config.series.map((label,s)=>[label,[...selected].filter(id=>Number(id.split(':')[1])===s).reduce((sum,id)=>sum+BigInt(config.points[Number(id.split(':')[0])].values[s]),0n)]);
                }
                if(config.mode==='items'&&config.series.length>1)totals.unshift([controls.dataset.totalLabel,totals.reduce((sum,entry)=>sum+entry[1],0n)]);
                controls.querySelector('[data-selection-period]').textContent=range ? config.points[indices[0]].label+' – '+config.points[indices[indices.length-1]].label : indices.map(i=>config.points[i].label).join(' · ');
                values.replaceChildren();
                totals.forEach(([label,value])=>{const item=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.className='subtle-copy';dt.textContent=label;dd.className='text-xl font-semibold tabular-nums';dd.textContent=money(value);item.append(dt,dd);values.append(item);});
                if (range && highlight) {const first=indices[0],last=indices[indices.length-1];highlight.setAttribute('x',config.points[first].x-10);highlight.setAttribute('width',config.points[last].x-config.points[first].x+20);highlight.removeAttribute('hidden');}
            }
            function chooseRange(first,last) {
                close();
                selected.clear();range=[first,last];
                for(let i=Math.min(first,last);i<=Math.max(first,last);i++) config.series.forEach((_,s)=>selected.add(i+':'+s));
                render();
            }
            function choose(mark,additive) {
                if (!mark) return;
                close();
                range=null;keyboardAnchor=null;
                const id=key(mark);if(!additive) selected.clear();
                if(selected.has(id)) selected.delete(id);else selected.add(id);
                render();
            }
            const popover=document.createElement('div');popover.className='chart-composition';popover.hidden=true;popover.setAttribute('role','region');
            popover.id='chart-composition-'+serial;popover.tabIndex=0;popover.setAttribute('aria-label',controls.dataset.detailsLabel);
            const header=document.createElement('div');header.className='chart-composition-header';
            const title=document.createElement('strong');title.className='min-w-0 break-words';title.textContent=controls.dataset.detailsLabel;
            const closeButton=document.createElement('button');closeButton.type='button';closeButton.className='action-primary shrink-0';closeButton.textContent=controls.dataset.detailsClose;
            header.append(title,closeButton);
            const content=document.createElement('div');content.setAttribute('aria-live','polite');popover.append(header,content);document.body.append(popover);
            marks.forEach(mark=>{if(config.points[Number(mark.dataset.point)].details?.[Number(mark.dataset.series)]){mark.setAttribute('aria-controls',popover.id);mark.setAttribute('aria-expanded','false');}});
            let generation=0,currentUrl='',opener=null,controller=null;
            const openingScrolls=new Map();
            const scrollPosition=node=>node===document?[scrollX,scrollY]:[node.scrollLeft,node.scrollTop];
            function scrollChanged(node){const before=openingScrolls.get(node),now=scrollPosition(node);return !before||before.some((value,index)=>value!==now[index]);}
            function close(restoreFocus=false){
                generation++;controller?.abort();
                if(restoreFocus&&popover.contains(document.activeElement)&&opener?.isConnected)opener.focus({preventScroll:true});
                opener?.setAttribute('aria-expanded','false');popover.hidden=true;currentUrl='';opener=null;
            }
            closeButton.addEventListener('click',()=>close(true));
            popover.addEventListener('click',event=>{if(event.target.closest('a[href]'))close();});
            // Check after native Tab assigns its destination. Pointer clicks
            // on panel text must not dismiss it merely because focus changes.
            popover.addEventListener('keydown',event=>{if(event.key==='Tab')setTimeout(()=>{if(!popover.hidden&&!popover.contains(document.activeElement))close();},0);});
            function position(mark) {
                const box=(isSvg && mark.firstElementChild?mark.firstElementChild:mark).getBoundingClientRect();
                const bounds=popover.getBoundingClientRect();
                popover.style.left=Math.max(12,Math.min(box.x,innerWidth-bounds.width-12))+'px';
                popover.style.top=Math.max(72,Math.min(box.bottom+8,innerHeight-bounds.height-12))+'px';
            }
            async function inspect(mark,focusPanel=false) {
                const i=Number(mark.dataset.point),s=Number(mark.dataset.series),url=config.points[i].details?.[s];
                if(!url)return;
                if(currentUrl===url&&!popover.hidden){
                    if(opener!==mark){opener?.setAttribute('aria-expanded','false');opener=mark;mark.setAttribute('aria-expanded','true');}
                    if(focusPanel)popover.focus({preventScroll:true});return;
                }
                active.forEach(state=>{if(state.root!==root)state.close();});
                close();currentUrl=url;opener=mark;openingScrolls.clear();openingScrolls.set(document,scrollPosition(document));
                for(let parent=mark.parentElement;parent;parent=parent.parentElement)openingScrolls.set(parent,scrollPosition(parent));
                mark.setAttribute('aria-expanded','true');const version=++generation;
                title.textContent=controls.dataset.detailsLabel;content.textContent=controls.dataset.detailsLoading;popover.hidden=false;position(mark);
                // Ctrl opens a persistent panel so it can be released before
                // scrolling. Keyboard opening moves focus into that panel.
                if(focusPanel)popover.focus({preventScroll:true});
                try {
                    controller=new AbortController();
                    let data=cache.get(url);
                    if(!data){const response=await fetch(url,{credentials:'same-origin',signal:controller.signal});if(!response.ok)throw new Error('unavailable');data=await response.json();if(cache.size>100)cache.clear();cache.set(url,data);}
                    if(version!==generation||!root.isConnected)return;
                    content.replaceChildren();title.textContent=data.title;
                    const ul=document.createElement('ul');ul.className='mt-3 space-y-2';content.append(ul);
                    function rowContent(target,labelText,cents,disclosure=false){
                        const label=document.createElement('span'),amount=document.createElement('strong');
                        target.className='chart-composition-row';label.className='chart-composition-label min-w-0 break-words';label.textContent=labelText;
                        amount.className='shrink-0 tabular-nums';amount.textContent=money(BigInt(cents),data.currency);
                        if(target.tagName==='A'||disclosure){
                            const icon=document.createElementNS('http://www.w3.org/2000/svg','svg'),path=document.createElementNS('http://www.w3.org/2000/svg','path');
                            icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('aria-hidden','true');icon.setAttribute('class','inline-block h-3.5 w-3.5 align-middle text-forest/50 dark:text-night-muted');
                            icon.setAttribute('fill','none');icon.setAttribute('stroke','currentColor');icon.setAttribute('stroke-width','1.5');
                            path.setAttribute('d',disclosure?'m9 5 7 7-7 7':'M5 12h14m-6-6 6 6-6 6');icon.append(path);label.append(' ',icon);
                        }
                        target.append(label,amount);
                    }
                    function sourceLink(source,label=source.label,cents=source.cents){
                        const link=document.createElement('a');link.href=source.url;link.title=source.label;link.setAttribute('aria-label',source.action+': '+source.label+' · '+money(BigInt(cents),data.currency));
                        rowContent(link,label,cents);return link;
                    }
                    data.rows.forEach(row=>{
                        const li=document.createElement('li'),sources=row.sources||[];
                        if(sources.length===1)li.append(sourceLink(sources[0],row.label,row.cents));
                        else if(sources.length>1){
                            const details=document.createElement('details'),summary=document.createElement('summary'),entries=document.createElement('ul');
                            details.className='chart-composition-group';summary.title=controls.dataset.detailsSources;rowContent(summary,row.label,row.cents,true);
                            entries.className='chart-composition-sources';
                            sources.forEach(source=>{const item=document.createElement('li');item.append(sourceLink(source));entries.append(item);});
                            details.append(summary,entries);li.append(details);
                        }else{const plain=document.createElement('div');rowContent(plain,row.label,row.cents);li.append(plain);}
                        ul.append(li);
                    });
                    window.htmx?.process(content);
                    if(!data.rows.length){const p=document.createElement('p');p.textContent=controls.dataset.detailsEmpty;content.append(p);}
                    if(data.missing.length){const p=document.createElement('p');p.textContent=controls.dataset.detailsMissing+': '+data.missing.join(', ');content.append(p);}
                    position(mark);
                } catch(error){if(error.name!=='AbortError'&&version===generation)content.textContent=controls.dataset.detailsError;}
            }
            function clear(restoreFocus=false){selected.clear();range=null;keyboardAnchor=null;render();close(restoreFocus);}
            active.set(root,{root,clear,close,popover,scrollChanged,contains:node=>surface.contains(node)||controls.contains(node)||popover.contains(node)||marks.some(mark=>mark.contains(node))});
            const getMark=target=>{const mark=target.closest('[data-point]');return marks.includes(mark)?mark:null;};
            function nearest(event){const x=new DOMPoint(event.clientX,event.clientY).matrixTransform(surface.getScreenCTM().inverse()).x;return config.points.reduce((best,p,i)=>Math.abs(p.x-x)<Math.abs(config.points[best].x-x)?i:best,0);}
            let anchor=null,touchTimer=null,touchStart=null,touchHeld=false;
            root.addEventListener('pointerdown',event=>{
                const mark=getMark(event.target);if(event.button!==0||(!surface.contains(event.target)&&!mark))return;
                if(event.ctrlKey)return;
                if(event.pointerType==='touch'){
                    touchHeld=false;touchStart={x:event.clientX,y:event.clientY};
                    if(mark)touchTimer=setTimeout(()=>{touchHeld=true;inspect(mark);},500);
                    return;
                }
                event.preventDefault();
                if(items||event.shiftKey){choose(mark,event.shiftKey);return;}
                keyboardAnchor=null;anchor=nearest(event);chooseRange(anchor,anchor);surface.setPointerCapture(event.pointerId);
            });
            root.addEventListener('pointermove',event=>{
                const mark=getMark(event.target);hovered=mark?{mark,inspect}:null;
                if(event.pointerType==='touch'&&touchStart&&Math.hypot(event.clientX-touchStart.x,event.clientY-touchStart.y)>8){clearTimeout(touchTimer);touchStart=null;}
                if(event.ctrlKey&&mark&&!controlDismissed)inspect(mark);
                if(anchor!==null)chooseRange(anchor,nearest(event));
            });
            root.addEventListener('pointerup',event=>{
                clearTimeout(touchTimer);
                if(event.pointerType==='touch'&&touchStart&&!touchHeld){const mark=getMark(event.target);if(config.mode==='change'&&mark){const index=Number(mark.dataset.point);if(keyboardAnchor===null){keyboardAnchor=index;chooseRange(index,index);}else{chooseRange(keyboardAnchor,index);keyboardAnchor=null;}}else choose(mark,true);}
                anchor=null;touchStart=null;
            });
            root.addEventListener('pointercancel',()=>{clearTimeout(touchTimer);anchor=null;touchStart=null;});
            root.addEventListener('pointerleave',()=>{hovered=null;});
            root.addEventListener('focusin',()=>{hovered=null;});
            root.addEventListener('keydown',event=>{
                const mark=getMark(event.target);if(!mark)return;
                // A new hover wins over focus retained by a previous chart.
                // Moving keyboard focus clears that pointer context again.
                if(event.key==='Control'){event.preventDefault();if(!event.repeat){if(hovered?.mark.isConnected)hovered.inspect(hovered.mark);else inspect(mark,true);}return;}
                if(!['Enter',' '].includes(event.key))return;event.preventDefault();
                if(items||event.shiftKey){choose(mark,event.shiftKey);return;}
                const index=Number(mark.dataset.point);
                if(keyboardAnchor===null){keyboardAnchor=index;chooseRange(index,index);}else{chooseRange(keyboardAnchor,index);keyboardAnchor=null;}
            });
        });
    }
    // A second Ctrl dismisses instead of immediately reopening on the mark
    // beneath the pointer. Keep that press suppressed until it is released.
    document.addEventListener('keydown',event=>{
        if(event.key!=='Control'||event.repeat)return;
        const open=Array.from(active.values()).filter(state=>!state.popover.hidden);
        if(open.length){open.forEach(state=>state.close(true));controlDismissed=true;event.preventDefault();event.stopPropagation();}
    },true);
    document.addEventListener('keyup',event=>{if(event.key==='Control')controlDismissed=false;});
    function dismissOutside(event){
        active.forEach(state=>{
            if(!state.popover.hidden&&!state.popover.contains(event.target)){
                // Native focus can queue a scroll before Ctrl opens the panel.
                // Ignore that delayed event unless its position changed since opening.
                if(event.type==='scroll'&&!state.scrollChanged(event.target))return;
                state.close();if(event.ctrlKey)controlDismissed=true;
            }
        });
    }
    document.addEventListener('pointerdown',dismissOutside,true);
    // Keyboard activation has no pointerdown. A touch hold's release belongs
    // to its opener and must leave the newly opened panel available.
    document.addEventListener('click',event=>{if(event.detail===0)dismissOutside(event);},true);
    document.addEventListener('wheel',dismissOutside,{capture:true,passive:true});
    document.addEventListener('scroll',dismissOutside,true);
    document.addEventListener('pointerdown',event=>active.forEach(state=>{if(!state.contains(event.target))state.clear();}));
    document.addEventListener('keydown',event=>{if(event.key==='Escape')active.forEach(state=>state.clear(true));if(event.key==='Control'&&!event.repeat&&hovered?.mark.isConnected&&!event.target.closest('[data-point]'))hovered.inspect(hovered.mark);});
    document.addEventListener('htmx:beforeSwap',event=>{const target=event.detail?.target;if(target)active.forEach(state=>{if(target.contains(state.root))state.close();});});
    window.TuxedoChartSelection={initialize};
    document.addEventListener('DOMContentLoaded',initialize);document.addEventListener('htmx:load',initialize);document.addEventListener('htmx:historyRestore',initialize);
})();
