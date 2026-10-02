async function refreshQueue(){
  try{
    const res=await fetch('/api/queue'); const data=await res.json();
    const body=document.getElementById('queueBody');
    if(!data.length){body.innerHTML='<tr><td colspan="4" class="text-center py-5 text-muted">No active tokens.</td></tr>';return;}
    body.innerHTML=data.map(r=>`<tr><td class="fw-bold fs-4">${r.token}</td><td>${r.service_name}</td><td>${r.appointment_time}</td><td><span class="badge status-${r.status} text-capitalize">${r.status}</span></td></tr>`).join('');
  }catch(e){console.error(e)}
}
setInterval(refreshQueue,4000);
