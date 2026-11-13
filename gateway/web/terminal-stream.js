'use strict';
(() => {
 const replies=/^(?:\x1b\[[0-?]*[RcntIO]|\x1bP[^\x1b]{0,512}\x1b\\)+$/;
 class TerminalStream {
  constructor(terminal){this.terminal=terminal;this.startup=true;this.generation=0;this.queue=Promise.resolve();}
  reset(){const generation=++this.generation;this.startup=true;this.queue=this.queue.catch(()=>{}).then(()=>{if(generation===this.generation)this.terminal.reset();});return this.queue;}
  input(data){if(data&&!replies.test(data))this.startup=false;}
  raw(data){return new Promise(resolve=>this.terminal.write(data,resolve));}
  async trim(){
   const buffer=this.terminal.buffer.active;if(!this.startup||!buffer.baseY)return;
   for(let i=0;i<buffer.baseY;i++)if(buffer.getLine(i)?.translateToString(true).trim())return;
   await this.raw('\x1b[3J');
  }
  write(data){
   const generation=this.generation;
   this.queue=this.queue.catch(()=>{}).then(async()=>{
    if(generation!==this.generation)return;
    if(!this.startup){await this.raw(data);return;}
    let start=0;
    for(let i=0;i<data.length;i++)if(data[i]===10){
     if(generation!==this.generation)return;
     await this.raw(data.subarray(start,i+1));start=i+1;
     if(generation===this.generation)await this.trim();
    }
    if(start<data.length&&generation===this.generation)await this.raw(data.subarray(start));
   });return this.queue;
  }
 }
 window.TerminalStream=TerminalStream;
})();
