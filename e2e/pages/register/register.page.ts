import type { Page } from "@playwright/test";
import { register, type RegistrationDetails } from "./register.actions";
export class RegisterPage { constructor(private readonly page: Page) {} async goto(): Promise<void> { await this.page.goto("/register"); } async register(details: RegistrationDetails): Promise<void> { await register(this.page, details); } }
