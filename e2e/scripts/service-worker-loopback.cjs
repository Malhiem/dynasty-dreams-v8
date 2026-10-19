// Browser-only loopback proxy: the Compose API/fixtures still use http://web.
const http=require('node:http');
if(process.env.E2E_BASE_URL!=='http://web'||process.env.H2H_ISOLATED!=='1')throw Error('Requires disposable E2E Compose stack');
http.createServer((request,response)=>{
 const upstream=http.request({hostname:'web',port:80,path:request.url,method:request.method,headers:{...request.headers,host:'web'}},result=>{response.writeHead(result.statusCode,result.headers);result.pipe(response);});
 upstream.on('error',()=>{response.writeHead(502);response.end();});request.pipe(upstream);
}).listen(8080,'127.0.0.1');
