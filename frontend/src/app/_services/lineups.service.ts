import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

import { BaseService } from './base.service';
import { LineupApiResponse, LineupQueryOptions, LineupSummary } from '../_models/lineup';

@Injectable({ providedIn: 'root' })
export class LineupsService extends BaseService {
  constructor(protected override http: HttpClient) {
    super(http);
  }

  private buildQueryParams(queryParams: Record<string, string | number>): HttpParams {
    return Object.entries(queryParams).reduce(
      (params, [key, value]) => params.set(key, String(value)),
      new HttpParams(),
    );
  }

  private buildDisplayedEndpointWithParams(
    endpoint: string,
    queryParams: Record<string, string | number>,
  ): string {
    const queryString = new URLSearchParams(
      Object.entries(queryParams).map(([key, value]) => [key, String(value)]),
    ).toString();
    return queryString ? `${endpoint}?${queryString}` : endpoint;
  }

  getLineupsLeagueSummary(optionsOrSize: LineupQueryOptions | number = {}): Observable<LineupApiResponse> {
    const endpoint = `${this.baseUrl}/lineups`;
    const options = typeof optionsOrSize === 'number' ? { lineup_size: optionsOrSize } : optionsOrSize;
    const queryParams: Record<string, string | number> = {};
    for (const [key, value] of Object.entries({ lineup_size: 5, ...options })) {
      if (value !== undefined && value !== null && value !== '') {
        queryParams[key] = value;
      }
    }
    const params = this.buildQueryParams(queryParams);
    const displayedEndpointWithParams = this.buildDisplayedEndpointWithParams(endpoint, queryParams);

    return this.get<LineupSummary[]>(endpoint, params).pipe(
      map((data) => ({
        endpoint: displayedEndpointWithParams,
        apiResponse: data,
      })),
    );
  }
}
