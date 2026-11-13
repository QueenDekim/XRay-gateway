import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import headless from '@xterm/headless';

const {Terminal}=headless;

const context=vm.createContext({window:{}});
vm.runInContext(fs.readFileSync(new URL('../gateway/web/terminal-stream.js',import.meta.url),'utf8'),context);
const TerminalStream=context.window.TerminalStream;
const banner=[
 '  MMM      MMM       KKK                          TTTTTTTTTTT      KKK',
 '  MMMM    MMMM       KKK                          TTTTTTTTTTT      KKK',
 '  MMM MMMM MMM  III  KKK  KKK  RRRRRR     OOOOOO      TTT     III  KKK  KKK',
 '  MMM  MM  MMM  III  KKKKK     RRR  RRR  OOO  OOO     TTT     III  KKKKK',
 '  MMM      MMM  III  KKK KKK   RRRRRR    OOO  OOO     TTT     III  KKK KKK',
 '  MMM      MMM  III  KKK  KKK  RRR  RRR   OOOOOO      TTT     III  KKK  KKK',
 '', '  MikroTik RouterOS 7.19.4', '', '', 'Press F1 for help', '', '', '[panel@router] > '
].join('\r\n');
const probe='\r\x1b[9999B  \x1b[6n\x1b[HĚH\x1b[6n\x1b[2J\x1b[H\x1b[9999B'+'\r\n'.repeat(33);
function lines(terminal){const buffer=terminal.buffer.active;return Array.from({length:buffer.length},(_,i)=>buffer.getLine(i).translateToString(true));}
async function startup(rows,size){
 const terminal=new Terminal({cols:100,rows,scrollback:2000,allowProposedApi:true});
 const stream=new TerminalStream(terminal),replies=[];
 terminal.onData(data=>{replies.push(data);stream.input(data);});
 await stream.reset();
 const bytes=Buffer.from(probe+banner);
 for(let i=0;i<bytes.length;i+=size)await stream.write(bytes.subarray(i,i+size));
 return{terminal,stream,replies};
}
for(const size of [1,7,10000]){
 const {terminal,stream,replies}=await startup(30,size);
 const contents=lines(terminal),needed=30-banner.split('\n').length;
 assert.equal(terminal.buffer.active.baseY,0,'Startup must leave no blank scrollback');
 assert.equal(contents.findIndex(line=>line.trim()),needed,'Only visible padding above the logo should remain');
 assert.equal(terminal.buffer.active.cursorY,29,'The prompt stays at the bottom of the first screen');
 assert.ok(contents.join('\n').includes('MMM      MMM'));
 assert.ok(replies.includes('\x1b[30;3R'),'Screen-height probing must still work');
 stream.input('/system resource print\r');
 const later=Buffer.from('\r\n'.repeat(40)+'later output\r\n');await stream.write(later);
 assert.ok(terminal.buffer.active.baseY>0,'Command output keeps its scrollback');
 assert.ok(lines(terminal).join('\n').includes('later output'));
 terminal.dispose();
}
{
 const {terminal}=await startup(8,5);
 const contents=lines(terminal);
 assert.equal(contents.findIndex(line=>line.trim()),0,'A small viewport must retain the full banner in history');
 assert.ok(contents.join('\n').includes('MikroTik RouterOS'));
 assert.ok(contents.join('\n').includes('MMM      MMM'));
 terminal.dispose();
}
console.log('REAL XTERM / SCREEN-HEIGHT REPLIES / EXACT FIRST-SCREEN PADDING / FRAGMENTED INPUT / PRESERVED COMMAND HISTORY PASS');
