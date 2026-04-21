// @ts-nocheck
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";

interface TeamLinkProps {
  name: string;
  className?: string;
  children?: React.ReactNode;
}

const TeamLink = ({ name, className, children }: TeamLinkProps) => {
  const navigate = useNavigate();

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    const slug = name.toLowerCase().replace(/\s+/g, "-");
    navigate(`/team?team=${slug}`);
  };

  return (
    <span
      onClick={handleClick}
      className={cn(
        "cursor-pointer hover:text-primary hover:underline transition-colors",
        className
      )}
    >
      {children || name}
    </span>
  );
};

export default TeamLink;
