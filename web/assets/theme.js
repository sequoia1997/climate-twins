// Applies the saved light/dark choice before the page paints (loaded in <head> on every page).
try{var t=localStorage.getItem("ct-theme");if(t==="dark"||t==="light")document.documentElement.setAttribute("data-theme",t);}catch(e){}
