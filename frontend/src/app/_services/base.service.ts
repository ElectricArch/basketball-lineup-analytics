import { HttpClient, HttpHeaders, HttpParams, HttpParameterCodec } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export class BaseService {
  protected get headers(): HttpHeaders { return new HttpHeaders(); }
  protected baseUrl = environment.BACKEND_PUBLIC_DOMAIN.trim().replace(/\/$/, '') + '/api/v1';

  constructor(protected http: HttpClient) {}

  protected get<T = unknown>(url: string, params?: HttpParams): Observable<T> {
    const domain = environment.BACKEND_PUBLIC_DOMAIN.trim();
    let valid = false;
    try {
      const configured = new URL(domain);
      const local = ['127.0.0.1', 'localhost', '[::1]'].includes(configured.hostname);
      valid = !configured.username && !configured.password && !configured.search &&
        !configured.hash && (configured.pathname === '/' || configured.pathname === '') &&
        (configured.protocol === 'https:' || (configured.protocol === 'http:' && local));
    } catch { valid = false; }
    if (!domain || !valid) {
      return throwError(() => ({
        status: 0,
        errorMessages: ['Configure an independent backend address before requesting lineup data.'],
      } as HttpErrorResponse));
    }
    return this.http.get<T>(url, { headers: this.headers, params }).pipe(
      catchError((error: { status?: number }) => throwError(() => ({
        status: error.status ?? 0,
        errorMessages: [error.status === 429
          ? 'Request limit reached. Wait and retry.'
          : 'Lineup data is unavailable. Try again later.'],
      } as HttpErrorResponse))),
    );
  }
}

export class HttpErrorResponse {
  status!: number;
  errorMessages!: string[];
}

export class CustomHttpParamEncoder implements HttpParameterCodec {
  encodeKey(key: string): string { return encodeURIComponent(key); }
  encodeValue(value: string): string { return encodeURIComponent(value); }
  decodeKey(key: string): string { return decodeURIComponent(key); }
  decodeValue(value: string): string { return decodeURIComponent(value); }
}
