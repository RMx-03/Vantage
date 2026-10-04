export interface AuthUser {
  id: string;
  email: string;
  email_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}
