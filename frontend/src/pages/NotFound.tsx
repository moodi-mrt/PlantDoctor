import { ButtonLink, EmptyState } from "../components/ui/ui";
export default function NotFound() {
  return <div className="mx-auto max-w-lg px-5 py-20"><EmptyState icon="search" title="Page not found" action={<ButtonLink to="/">Go home</ButtonLink>}>The page you're looking for doesn't exist or has moved.</EmptyState></div>;
}
