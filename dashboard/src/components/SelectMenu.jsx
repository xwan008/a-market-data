import React, {useEffect, useId, useRef, useState} from 'react';
import {Check, ChevronDown} from 'lucide-react';

/** One visual and keyboard interaction language for dashboard filters. */
export default function SelectMenu({value,onChange,options,label='选择',className='',disabled=false,leadingIcon:LeadingIcon}){
 const items=(Array.isArray(options)?options:[]).map(option=>typeof option==='string'?{value:option,label:option}:option);
 const selected=items.find(option=>option.value===value)||items[0];
 const [open,setOpen]=useState(false);
 const [cursor,setCursor]=useState(0);
 const rootRef=useRef(null),triggerRef=useRef(null),listRef=useRef(null);
 const id=useId().replace(/:/g,'');
 useEffect(()=>{
  if(!open)return;
  const closeOutside=event=>{if(!rootRef.current?.contains(event.target))setOpen(false)};
  document.addEventListener('pointerdown',closeOutside);
  listRef.current?.focus();
  return ()=>document.removeEventListener('pointerdown',closeOutside);
 },[open]);
 useEffect(()=>{
  if(open)setCursor(Math.max(0,items.findIndex(option=>option.value===value)));
 },[open,value]);
 const pick=index=>{
  const item=items[index];
  if(!item)return;
  onChange(item.value);
  setOpen(false);
  triggerRef.current?.focus();
 };
 const handleKeys=event=>{
  if(disabled||!items.length)return;
  if(!open){
   if(['Enter',' ','ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();setOpen(true)}
   return;
  }
  if(event.key==='Escape'){event.preventDefault();setOpen(false);triggerRef.current?.focus()}
  else if(event.key==='Tab')setOpen(false);
  else if(event.key==='ArrowDown'){event.preventDefault();setCursor(index=>Math.min(items.length-1,index+1))}
  else if(event.key==='ArrowUp'){event.preventDefault();setCursor(index=>Math.max(0,index-1))}
  else if(event.key==='Home'){event.preventDefault();setCursor(0)}
  else if(event.key==='End'){event.preventDefault();setCursor(items.length-1)}
  else if(event.key==='Enter'||event.key===' '){event.preventDefault();pick(cursor)}
 };
 return <div className={'ui-select '+className+(open?' is-open':'')} ref={rootRef} onKeyDown={handleKeys}>
  <button type="button" ref={triggerRef} className="ui-select-trigger" aria-label={label} aria-haspopup="listbox" aria-expanded={open} aria-controls={open?id+'-options':undefined} disabled={disabled||!items.length} onClick={()=>setOpen(current=>!current)}>
   {LeadingIcon&&<LeadingIcon size={16} className="ui-select-leading" aria-hidden="true"/>}
   <span className="ui-select-value">{selected?.label||'暂无可选项目'}</span>
   <ChevronDown size={16} className="ui-select-chevron" aria-hidden="true"/>
  </button>
  {open&&<div className="ui-select-options" id={id+'-options'} ref={listRef} role="listbox" tabIndex={-1} aria-label={label} aria-activedescendant={id+'-option-'+cursor}>
   {items.map((item,index)=><button type="button" key={String(item.value)} id={id+'-option-'+index} role="option" aria-selected={item.value===value} tabIndex={-1} className={'ui-select-option'+(cursor===index?' is-highlighted':'')+(item.value===value?' is-selected':'')} onMouseEnter={()=>setCursor(index)} onClick={()=>pick(index)}>
    <span>{item.label}</span>{item.value===value&&<Check size={14} aria-hidden="true"/>}
   </button>)}
  </div>}
 </div>;
}
