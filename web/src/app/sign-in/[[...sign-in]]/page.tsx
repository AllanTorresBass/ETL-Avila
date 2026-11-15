import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center py-12">
      <SignIn
        appearance={{
          variables: {
            colorPrimary: "#0F7A33",
            borderRadius: "1rem",
          },
        }}
      />
    </div>
  );
}
